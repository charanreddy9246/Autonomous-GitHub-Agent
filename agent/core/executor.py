import re
import time

from agent.github_client import GitHubAPIError
from agent.memory import capability_memory
from agent.synthesis.synthesizer import Synthesizer

MAX_REPLANS = 1


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:48] or "synthesized_tool"


class Executor:
    def __init__(self, registry, client, planner):
        self.registry = registry
        self.client = client
        self.planner = planner
        self.synthesizer = Synthesizer()

    def run(self, instruction: str, steps: list[dict], tool_specs: list[dict]) -> dict:
        results = []
        i = 0
        aborted = False
        replans_used = 0
        start = time.monotonic()

        while i < len(steps):
            step = steps[i]
            tool = step.get("tool")
            args = self._resolve_args(step.get("args", {}), results)
            critical = bool(step.get("critical", False))

            if tool == "__missing__":
                result = self._handle_missing(step, args)
                results.append(result)
                if not result["success"] and critical:
                    aborted = True
                    self._skip_rest(steps, i + 1, results, f"aborted: prerequisite capability synthesis failed ({step.get('capability_request')})")
                    break
                i += 1
                continue

            outcome = self._call_tool(tool, args)
            if outcome["success"]:
                capability_memory.record_result(tool, True)
                results.append({"tool": tool, "args": args, "success": True, "result": outcome["result"]})
                i += 1
                continue

            capability_memory.record_result(tool, False)
            error_msg = outcome["error"]

            if not critical:
                results.append({"tool": tool, "args": args, "success": False, "error": error_msg, "note": "non-critical, continuing"})
                i += 1
                continue

            # critical step failed: try at most MAX_REPLANS replans for the whole run
            replanned = None
            if replans_used < MAX_REPLANS:
                try:
                    remaining = steps[i + 1:]
                    replanned = self.planner.replan_after_failure(
                        instruction, tool_specs, {"tool": tool, "args": args}, error_msg, remaining
                    )
                    replans_used += 1
                except Exception as replan_exc:  # noqa: BLE001
                    error_msg += f" | replan also failed: {replan_exc}"

            if replanned is not None:
                capability_memory.add_constraint(tool, f"observed failure: {error_msg}")
                steps = steps[: i] + replanned
                results.append({"tool": tool, "args": args, "success": False, "error": error_msg, "note": "replanned after this failure"})
                i += 1
                continue

            results.append({"tool": tool, "args": args, "success": False, "error": error_msg, "note": "critical, no viable replan"})
            aborted = True
            self._skip_rest(steps, i + 1, results, f"aborted: critical step '{tool}' failed with no recovery: {error_msg}")
            break

        total_time = time.monotonic() - start
        outcome = "failed" if all(not r.get("success") for r in results) else ("partial" if (aborted or any(not r.get("success") for r in results)) else "success")
        return {
            "steps_result": results,
            "outcome": outcome,
            "total_time_s": total_time,
            "final_steps": steps,
        }

    def _call_tool(self, tool: str, args: dict) -> dict:
        try:
            result = self.registry.call(tool, args, self.client)
            return {"success": True, "result": result}
        except GitHubAPIError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"{type(e).__name__}: {e}"}

    def _handle_missing(self, step: dict, args: dict) -> dict:
        request = step.get("capability_request", "unnamed capability")
        name = _slugify(request)
        synth_result = self.synthesizer.synthesize(name, request, args)
        if synth_result["success"]:
            self.registry.register_synthesized(name, synth_result["code"], synth_result["description"], synth_result["parameters"])
            capability_memory.record_result(name, True)
            return {
                "tool": name,
                "args": args,
                "success": True,
                "result": synth_result["result"],
                "api_calls": synth_result.get("api_calls", 0),
                "note": f"capability synthesized at runtime after {len(synth_result['attempts'])} attempt(s) and registered for reuse",
            }
        return {
            "tool": name,
            "args": args,
            "success": False,
            "error": synth_result.get("final_error"),
            "note": f"capability synthesis failed after {len(synth_result['attempts'])} attempts",
            "attempts": synth_result["attempts"],
        }

    def _resolve_args(self, args, results: list[dict]):
        """Replaces any string of the form "{{step:N}}" (0-based index into
        the results produced so far in this plan) with the actual result
        of that step, recursively through dicts/lists. Without this, the
        planner has no way to hand real data (e.g. the issue list from an
        earlier list_issues step) to a later step -- it can only pass a
        placeholder string, which is useless to the tool receiving it.

        Supports an optional dotted/indexed field path after the step index,
        e.g. "{{step:0.number}}" or "{{step:0.items[0].id}}", so a later step
        can pull one specific field out of an earlier step's result instead
        of always receiving the whole thing."""
        pattern = re.compile(r"^\{\{step:(\d+)((?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*)\}\}$")
        path_token = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")

        def navigate(value, path: str):
            for m in path_token.finditer(path):
                key, idx = m.group(1), m.group(2)
                if key is not None:
                    if not isinstance(value, dict) or key not in value:
                        return None
                    value = value[key]
                else:
                    i = int(idx)
                    if not isinstance(value, list) or i >= len(value):
                        return None
                    value = value[i]
            return value

        def resolve(value):
            if isinstance(value, str):
                m = pattern.match(value.strip())
                if m:
                    idx, path = int(m.group(1)), m.group(2)
                    if 0 <= idx < len(results) and results[idx].get("success"):
                        return navigate(results[idx]["result"], path)
                    return None
                return value
            if isinstance(value, dict):
                return {k: resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [resolve(v) for v in value]
            return value

        return resolve(args)

    def _skip_rest(self, steps, from_index, results, reason):
        for step in steps[from_index:]:
            results.append({"tool": step.get("tool"), "args": step.get("args", {}), "success": False, "skipped": True, "error": reason})

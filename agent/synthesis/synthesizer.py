import json
import os
import re

from openai import OpenAI

from agent.memory import capability_memory
from agent.synthesis import sandbox
from agent.util import safe_jsonify

SYNTH_MODEL = os.environ.get("SYNTH_MODEL", "gpt-4o-mini")
MAX_ATTEMPTS = 3

SYSTEM_PROMPT = """You write a single self-contained Python function to extend a
GitHub automation agent at runtime.

Requirements:
- Define exactly one function: def run(args: dict, client) -> dict | list
- `client` is a GitHubClient instance with methods:
    client.get(path, params=None) -> parsed JSON
    client.post(path, json=None) -> parsed JSON
    client.patch(path, json=None) -> parsed JSON
    client.delete(path) -> None
    client.repo_path(suffix: str) -> "/repos/{owner}/{repo}" + suffix
  All paths are relative to https://api.github.com and are auto-prefixed.
  `client` is ALREADY bound to one specific repo -- it knows the owner/repo
  internally. `client.repo_path(suffix)` already produces the full
  "/repos/{owner}/{repo}{suffix}" path.
  CORRECT:   client.get(client.repo_path("/contributors"))
  CORRECT:   client.get(client.repo_path("/issues"), params={"state": "open"})
  WRONG:     client.get(client.repo_path(f"/repos/{args['repository']}/contributors"))
             -- this duplicates the repo path and produces a broken URL like
             /repos/owner/repo/repos/owner/repo/contributors (404).
  If `args` happens to contain a "repository" or "owner/repo" style field,
  IGNORE it for path-building purposes -- `client.repo_path()` already
  targets the correct repo. Never concatenate an owner/repo string into the
  suffix passed to `client.repo_path()` or `client.get()`.
- Do not import anything except modules already available (no third-party
  imports beyond what's implicitly available: json, re, collections, itertools,
  datetime are fine to import inside the function if needed).
- Do not read files, use the network directly (only via `client`), or use
  subprocess/os.system/eval/exec.
- Return JSON-serializable data only (dict, list, str, int, float, bool, None).
- Raise a plain Exception with a clear message on any unrecoverable error.

Respond with a JSON object: {"code": "<the full function source, as a string>"}
"""


def _extract_code(raw_json: str) -> str:
    parsed = json.loads(raw_json)
    code = parsed["code"]
    code = re.sub(r"^```(python)?\n?|```$", "", code.strip(), flags=re.MULTILINE)
    return code


class Synthesizer:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.llm_call_count = 0

    def synthesize(self, capability_name: str, capability_request: str, test_args: dict) -> dict:
        """Returns a dict:
        {"success": bool, "name", "description", "parameters", "attempts": [...]}
        On success the capability has already been persisted to
        capability_memory (the caller is responsible for loading it into
        the live ToolRegistry).
        """
        attempts_log = []
        error_feedback = None
        code = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            user_content = {
                "capability_name": capability_name,
                "what_it_should_do": capability_request,
                "example_call_it_must_satisfy": {"args": test_args},
            }
            if error_feedback:
                user_content["previous_attempt_failed_with"] = error_feedback

            resp = self.client.chat.completions.create(
                model=SYNTH_MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(safe_jsonify(user_content))},
                ],
            )
            self.llm_call_count += 1
            try:
                code = _extract_code(resp.choices[0].message.content)
                ok, payload = sandbox.test_capability(code, test_args)
            except Exception as exc:  # noqa: BLE001 -- any unexpected failure in this
                # attempt (bad LLM output, a sandbox-side bug, anything) becomes a
                # normal failed attempt fed back for the next retry, instead of
                # propagating up and crashing the whole run.
                ok, payload = False, {"error": f"{type(exc).__name__}: {exc}"}
            attempts_log.append({"attempt": attempt, "ok": ok, "detail": payload})

            if ok:
                description = capability_request
                parameters = {"type": "object", "properties": {k: {} for k in test_args}}
                capability_memory.register_synthesized(capability_name, description, code, parameters)
                return {
                    "success": True,
                    "name": capability_name,
                    "description": description,
                    "parameters": parameters,
                    "code": code,
                    "result": payload.get("result"),
                    "api_calls": payload.get("api_calls", 0),
                    "attempts": attempts_log,
                }

            error_feedback = payload.get("error", "unknown error")

        return {
            "success": False,
            "name": capability_name,
            "attempts": attempts_log,
            "final_error": error_feedback,
        }

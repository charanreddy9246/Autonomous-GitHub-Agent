from agent.memory import capability_memory
from agent.tools.github_base import BASE_TOOLS, TOOL_SPECS as BASE_SPECS

SYNTHESIZED_FUNCTION_NAME = "run"


class ToolRegistry:
    def __init__(self):
        self._fns: dict[str, callable] = dict(BASE_TOOLS)
        self._specs: dict[str, dict] = {
            name: {"description": spec["description"], "parameters": spec["parameters"], "source": "base"}
            for name, spec in BASE_SPECS.items()
        }
        for name, spec in BASE_SPECS.items():
            capability_memory.ensure_base_registered(name, spec["description"], spec["parameters"])
        self._load_synthesized_from_memory()

    def _load_synthesized_from_memory(self) -> None:
        for cap in capability_memory.get_all():
            if cap["source"] == "synthesized" and cap["code"]:
                self._load_code(cap["name"], cap["code"], cap["description"], cap["parameters"])

    def _load_code(self, name: str, code: str, description: str, parameters: dict) -> None:
        namespace: dict = {}
        exec(code, namespace)  # noqa: S102 -- intentional: this is the synthesis mechanism
        fn = namespace.get(SYNTHESIZED_FUNCTION_NAME)
        if fn is None:
            raise ValueError(f"synthesized code for '{name}' does not define '{SYNTHESIZED_FUNCTION_NAME}'")
        self._fns[name] = fn
        self._specs[name] = {"description": description, "parameters": parameters, "source": "synthesized"}

    def register_synthesized(self, name: str, code: str, description: str, parameters: dict) -> None:
        """Load a freshly-synthesized tool into the live registry for this
        session. Persistence to capability_memory happens separately in
        the synthesizer once the tool has passed its sandbox test."""
        self._load_code(name, code, description, parameters)

    def has(self, name: str) -> bool:
        return name in self._fns

    def call(self, name: str, args: dict, client) -> object:
        return self._fns[name](args, client)

    def specs_for_planner(self) -> list[dict]:
        caps = {c["name"]: c for c in capability_memory.get_all()}
        out = []
        for name, spec in self._specs.items():
            cap = caps.get(name, {})
            success = cap.get("success_count", 0)
            failure = cap.get("failure_count", 0)
            rate = f"{success}/{success + failure}" if (success + failure) else "untested"
            out.append(
                {
                    "name": name,
                    "description": spec["description"],
                    "parameters": spec["parameters"],
                    "source": spec["source"],
                    "success_rate": rate,
                    "known_constraints": cap.get("constraints", []),
                }
            )
        return out

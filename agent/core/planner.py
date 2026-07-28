import json
import os

from openai import OpenAI

from agent.memory import execution_memory, similarity
from agent.util import safe_jsonify

PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "gpt-4o")

SYSTEM_PROMPT = """You are the planning module of an autonomous GitHub agent.
Given a natural language instruction, the list of tools currently available
(each with a name, description, JSON-schema parameters, historical success
rate, and any constraints discovered at runtime), and optionally a similar
past execution, produce a step-by-step execution plan.

Rules:
- Use ONLY tools from the provided list, and ONLY when a tool's description
  genuinely matches what a specific step needs to accomplish. Matching on
  vague topical overlap (e.g. both mention "repository" or "labels") is NOT
  enough -- the tool must actually produce or act on the specific data the
  step requires.
- Never force-fit an existing tool to a need it wasn't built for, and never
  call a tool with empty or placeholder args just because it exists. If no
  available tool's description satisfies a specific piece of the instruction,
  emit a step with "tool": "__missing__", a "capability_request" field
  describing in plain English what the missing tool must do, and still
  populate "args" with the concrete arguments that tool would need once it
  exists (this both triggers and seeds runtime capability synthesis).
- A compound instruction may need several DIFFERENT missing capabilities
  (e.g. one for repository metadata, another for file structure, another for
  commit activity) -- do not collapse them into whatever tool happens to
  already exist.
- Before finalizing the plan, explicitly enumerate every distinct thing the
  instruction asks for (in "reasoning") and make sure each one maps to at
  least one step -- either an existing tool, or a "__missing__" step. Do not
  silently drop a requested item because no tool covers it yet; a step that
  ends up returning "nothing found" is correct, an item with no step at all
  is not.
- Order steps so that data-gathering happens before actions that depend on it.
- To pass the result of an earlier step into a later step's args, use the
  exact string "{{step:N}}" (N = 0-based index of that step within THIS
  plan) as the arg value. It will be replaced with that step's real output
  before the later step runs.
- If a later step needs one specific field out of an earlier step's result
  rather than the whole thing (e.g. a tool returned {"number": 8, "url": ...}
  but the next step's parameter expects just a plain issue number), use
  "{{step:N.field_name}}" (dotted path; add "[i]" for list indices, e.g.
  "{{step:0.items[0].id}}"). Never pass a whole object where a tool's
  parameter schema expects a single scalar value (int/str) -- use the dotted
  path to extract the exact field instead. Do not invent any other
  placeholder syntax.
- If a similar past execution and its known constraints are provided, apply
  those lessons directly (e.g. create a label before assigning it, if that
  constraint is recorded) instead of re-discovering them by trial and error.
- Mark a step "critical": true if later steps cannot proceed without its
  output; otherwise false.
- Respond with JSON only, matching this shape:
{
  "reasoning": "short explanation of the plan",
  "steps": [
    {"tool": "<name or __missing__>", "args": {...}, "critical": true|false,
     "capability_request": "<only if tool is __missing__>"}
  ]
}
"""


class Planner:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.llm_call_count = 0

    def plan(self, instruction: str, tool_specs: list[dict]):
        """Returns (steps, embedding, reused_from: PastExecution|None)."""
        embedding = similarity.embed(instruction)
        reused_from = execution_memory.find_similar(embedding)

        user_content = {
            "instruction": instruction,
            "available_tools": tool_specs,
        }
        if reused_from is not None:
            user_content["similar_past_execution"] = {
                "instruction": reused_from.instruction_text,
                "similarity": round(reused_from.similarity_score, 3),
                "decomposition_used": reused_from.decomposition,
                "outcome": reused_from.outcome,
                "cost": {
                    "api_calls": reused_from.total_api_calls,
                    "llm_calls": reused_from.total_llm_calls,
                    "time_s": round(reused_from.total_time_s, 2),
                },
            }

        resp = self.client.chat.completions.create(
            model=PLANNER_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(safe_jsonify(user_content))},
            ],
        )
        self.llm_call_count += 1
        parsed = json.loads(resp.choices[0].message.content)
        return parsed["steps"], embedding, reused_from

    def replan_after_failure(self, instruction: str, tool_specs: list[dict], failed_step: dict, error: str, remaining_steps: list[dict]):
        """Called by the executor when a step fails in a way that looks
        recoverable (e.g. a validation error). Asks the planner to revise
        the remaining plan given the concrete error."""
        user_content = {
            "instruction": instruction,
            "available_tools": tool_specs,
            "failed_step": failed_step,
            "error": error,
            "remaining_steps": remaining_steps,
            "task": "Revise the remaining steps (may insert corrective steps) to work around this error.",
        }
        resp = self.client.chat.completions.create(
            model=PLANNER_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(safe_jsonify(user_content))},
            ],
        )
        self.llm_call_count += 1
        parsed = json.loads(resp.choices[0].message.content)
        return parsed["steps"]

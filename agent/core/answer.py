import json
import os

from openai import OpenAI

from agent.util import safe_jsonify

MODEL = os.environ.get("ANSWER_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = """You answer the user's original instruction in plain, readable
English using only the data provided from the steps that were executed. Do not
invent facts not present in the data. If some part of the instruction couldn't
be answered from the data (a step failed or was skipped), say so plainly.
Keep it concise -- a few sentences to a short paragraph, not a data dump."""


def generate_answer(instruction: str, steps_result: list[dict]) -> str:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    condensed = [
        {
            "tool": s.get("tool"),
            "success": s.get("success"),
            "result": s.get("result"),
            "error": s.get("error"),
        }
        for s in steps_result
    ]
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(safe_jsonify({"instruction": instruction, "step_data": condensed}))},
        ],
    )
    return resp.choices[0].message.content

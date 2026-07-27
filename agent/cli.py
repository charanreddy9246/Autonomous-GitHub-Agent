import sys

from dotenv import load_dotenv

load_dotenv()

from agent.core.answer import generate_answer
from agent.core.executor import Executor
from agent.core.planner import Planner
from agent.core.reporter import build_report, print_report
from agent.github_client import GitHubClient
from agent.memory import execution_memory
from agent.memory.db import init_db
from agent.tools.registry import ToolRegistry


def run_instruction(instruction: str) -> dict:
    init_db()
    registry = ToolRegistry()
    client = GitHubClient()
    planner = Planner()

    tool_specs = registry.specs_for_planner()
    steps, embedding, reused_from = planner.plan(instruction, tool_specs)

    executor = Executor(registry, client, planner)
    run_result = executor.run(instruction, steps, tool_specs)

    # client.call_count only reflects calls made in this process; calls made
    # by synthesized tools during their sandbox test happen in a subprocess
    # and are reported back via each step's "api_calls" field.
    synthesis_api_calls = sum(r.get("api_calls", 0) for r in run_result["steps_result"])
    total_api_calls = client.call_count + synthesis_api_calls

    answer_text = generate_answer(instruction, run_result["steps_result"])
    total_llm_calls = planner.llm_call_count + executor.synthesizer.llm_call_count + 1

    execution_memory.save_execution(
        instruction_text=instruction,
        embedding=embedding,
        decomposition=run_result["final_steps"],
        steps_result=run_result["steps_result"],
        outcome=run_result["outcome"],
        total_api_calls=total_api_calls,
        total_llm_calls=total_llm_calls,
        total_time_s=run_result["total_time_s"],
        reused_from_execution_id=reused_from.id if reused_from else None,
    )

    report = build_report(
        instruction=instruction,
        outcome=run_result["outcome"],
        steps_result=run_result["steps_result"],
        total_api_calls=total_api_calls,
        total_llm_calls=total_llm_calls,
        total_time_s=run_result["total_time_s"],
        reused_from=reused_from,
    )
    report["answer"] = answer_text
    return report


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python -m agent.cli "your instruction here"')
        sys.exit(1)
    instruction = " ".join(sys.argv[1:])
    try:
        report = run_instruction(instruction)
    except Exception as exc:  # noqa: BLE001 -- last-resort safety net: the agent
        # must always hand back a structured report, never a raw crash, even
        # when something unanticipated breaks outside the executor's own
        # per-step error handling.
        print_report(
            {
                "instruction": instruction,
                "outcome": "error",
                "summary": "An internal error stopped this run before it could produce a normal report.",
                "steps": [],
                "cost": {"api_calls": 0, "llm_calls": 0, "time_s": 0},
                "answer": f"Internal error: {type(exc).__name__}: {exc}",
            }
        )
        sys.exit(1)
    print_report(report)


if __name__ == "__main__":
    main()

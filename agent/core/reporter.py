def build_report(
    instruction: str,
    outcome: str,
    steps_result: list[dict],
    total_api_calls: int,
    total_llm_calls: int,
    total_time_s: float,
    reused_from,
) -> dict:
    done = [r for r in steps_result if r.get("success")]
    failed = [r for r in steps_result if not r.get("success") and not r.get("skipped")]
    skipped = [r for r in steps_result if r.get("skipped")]

    report = {
        "instruction": instruction,
        "outcome": outcome,
        "summary": f"{len(done)} step(s) succeeded, {len(failed)} failed, {len(skipped)} skipped.",
        "steps": steps_result,
        "cost": {
            "api_calls": total_api_calls,
            "llm_calls": total_llm_calls,
            "time_s": round(total_time_s, 2),
        },
        "decisions": [r["note"] for r in steps_result if r.get("note")],
    }

    if reused_from is not None:
        delta_api = reused_from.total_api_calls - total_api_calls
        delta_time = reused_from.total_time_s - total_time_s
        report["memory_comparison"] = {
            "reused_from_execution_id": reused_from.id,
            "similarity": round(reused_from.similarity_score, 3),
            "previous_run": {
                "api_calls": reused_from.total_api_calls,
                "time_s": round(reused_from.total_time_s, 2),
            },
            "this_run": {"api_calls": total_api_calls, "time_s": round(total_time_s, 2)},
            "improvement": {"api_calls_saved": delta_api, "time_saved_s": round(delta_time, 2)},
        }
    return report


def _preview(value, max_len: int = 400) -> str:
    text = str(value)
    if len(text) > max_len:
        return text[:max_len] + f"... [truncated, {len(text)} chars total]"
    return text


def print_report(report: dict) -> None:
    print("\n" + "=" * 70)
    print(f"INSTRUCTION: {report['instruction']}")
    print(f"OUTCOME: {report['outcome'].upper()}")
    print(report["summary"])
    if report.get("answer"):
        print("-" * 70)
        print("ANSWER:")
        print(report["answer"])
    print("-" * 70)
    for step in report["steps"]:
        status = "OK" if step.get("success") else ("SKIPPED" if step.get("skipped") else "FAILED")
        print(f"  [{status}] {step.get('tool')} args={step.get('args')}")
        if step.get("success") and "result" in step:
            print(f"           result: {_preview(step['result'])}")
        if step.get("error"):
            print(f"           error: {step['error']}")
        if step.get("note"):
            print(f"           note: {step['note']}")
    print("-" * 70)
    c = report["cost"]
    print(f"COST: {c['api_calls']} API calls | {c['llm_calls']} LLM calls | {c['time_s']}s")
    if "memory_comparison" in report:
        mc = report["memory_comparison"]
        print(f"MEMORY REUSE: matched execution #{mc['reused_from_execution_id']} "
              f"(similarity {mc['similarity']})")
        print(f"  previous run: {mc['previous_run']['api_calls']} API calls, {mc['previous_run']['time_s']}s")
        print(f"  this run:     {mc['this_run']['api_calls']} API calls, {mc['this_run']['time_s']}s")
        api_delta = mc["improvement"]["api_calls_saved"]
        time_delta = mc["improvement"]["time_saved_s"]
        api_msg = f"{api_delta} fewer API calls" if api_delta >= 0 else f"{-api_delta} MORE API calls (new capability was synthesized this run)"
        time_msg = f"{time_delta}s saved" if time_delta >= 0 else f"{-time_delta}s slower"
        print(f"  change:       {api_msg}, {time_msg}")
    print("=" * 70 + "\n")

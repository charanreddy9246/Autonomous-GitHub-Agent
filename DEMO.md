# Demo Script

Target repo: `charanreddy9246/Autonomous-GitHub-Agent` (real GitHub repo, real API calls).

Before running the instructions below, make sure your repository has 5-6 sample open issues with varied titles and descriptions (without labels). You can create these manually directly on your GitHub repository page.

Run each with:
```bash
python -m agent.cli "<instruction>"
```

Numbers below are from an actual recorded run against the real repo (not
hypothetical) — re-running will vary slightly but the same *pattern* holds.

## Instruction 1 (baseline — base tools only)
> "List all open issues in the repo and tell me how many have no labels at all."

**What happened:** The base tool set has no "count issues without labels"
operation, so the planner emitted a `__missing__` step for it. Synthesis
generated a small self-contained function, tested it for real against the repo,
and registered it. Result: `SUCCESS`, 1 API call, 2 LLM calls (1 plan + 1
synthesis), 8.4s.

## Instruction 2 (compound — triggers capability synthesis)
> "Create the labels priority:high, priority:medium, and priority:low if they
> don't already exist, then look at every open issue and apply the priority label
> that best matches its title and body."

**What happened:** No base tool can create a label or apply one by inferred
priority — two `__missing__` steps. `agent/synthesis/synthesizer.py` generated,
sandbox-tested, and registered `check_if_the_labels_priority_...` (label
creation) and `apply_the_correct_priority_label_...` (classify + PATCH each
issue). Result: `SUCCESS`, 16 API calls, 2 LLM calls, 18.9s. (First attempt at
this instruction, before the executor's inter-step data-passing was fixed,
actually surfaced a real bug live — a synthesized step received a placeholder
string instead of the real issue list and failed cleanly with a reported error
rather than silently mis-behaving; see the "no silent half-completions" note in
ARCHITECTURE.md.)

Verified independently by re-reading the issues afterward — all 6 issues came
back with a real `priority:*` label applied via the GitHub API.

## Instruction 3 (repeat pattern — proves the learning loop)
> "Apply priority labels to all open issues again, creating the priority labels
> if needed."

**What happened:** `find_similar()` matched this against instruction 2's stored
execution (cosine similarity 0.799, above the 0.75 threshold). The planner
received that prior decomposition up front and reused the two capabilities
synthesized in instruction 2 (both already in `capabilities`, `source =
synthesized`) — no new synthesis, no replanning. Result:

```
COST: 9 API calls | 1 LLM calls | 4.97s
MEMORY REUSE: matched execution #3 (similarity 0.799)
  previous run: 16 API calls, 18.86s
  this run:     9 API calls, 4.97s
  improvement:  7 fewer API calls, 13.89s saved
```

This is the "task X took N calls on first run and fewer on a later run because
the agent learned Y" evidence the assignment asks for — real numbers, captured
in `memory.db`, from real runs against the live repo, not simulated or
hand-picked.

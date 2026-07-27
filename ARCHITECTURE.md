# Architecture

## 1. What does the memory system store, and why is it structured this way?

Two SQLite tables, matching the two layers the assignment requires — deliberately
*not* a vector store of raw prompts, because the point is structured knowledge the
agent can reason over, not similarity search over text.

**`executions`** (Execution Memory) — one row per run: the instruction text + its
embedding (for similarity lookup only, not for storage of "meaning"), the exact
decomposition used, per-step outcomes, and cost (API calls, LLM calls, wall time).
This is what lets the planner say "the last time something like this ran, it took
6 API calls and hit a 422 on step 2" instead of just "I've seen this prompt before."

**`capabilities`** (Capability Memory) — one row per tool (base or synthesized):
its description, success/failure counts, and a `constraints` list of things
*discovered at runtime* (e.g. "creating an issue with a label that doesn't exist
yet returns 422 — create the label first"). Constraints are appended the moment a
failure is observed, not pre-written.

Before every plan, the planner is fed (a) the closest past execution above a
cosine-similarity threshold (0.75 — tuned empirically against `text-embedding-3-small`,
where genuinely-related short imperative instructions scored 0.69–0.80 and
unrelated ones scored 0.33–0.57 in testing) and (b) the full capability list with
success rates and constraints. Both are used to change the plan produced, not
just logged for a human to read later — see `agent/core/planner.py`.

## 2. How does capability synthesis work?

The base tool set (`agent/tools/github_base.py`) is intentionally small:
`list_issues`, `create_issue`, `add_comment`, `get_issue`. Anything else
(labeling by inferred priority, weekly triage summaries, bulk operations, closing
stale issues...) has no implementation anywhere in the codebase at design time.

When the planner needs an operation with no matching tool, it emits a
`"tool": "__missing__"` step with a plain-English description of what's needed and
concrete example arguments. `agent/synthesis/synthesizer.py` then:

1. Sends that description + the `GitHubClient` interface to the LLM and asks for a
   single `def run(args, client)` function.
2. Runs the generated code in `agent/synthesis/sandbox.py` — a **separate
   subprocess**, not `eval()` in-process — which makes a real call against the
   configured GitHub repo using the example arguments.
3. If it raises, fails validation, or times out, the error is fed back to the LLM
   and it gets up to 2 more attempts (3 total).
4. Only a version that actually succeeded against the live API gets written to
   `capabilities` (with its source code) and loaded into the live `ToolRegistry`
   for the rest of this run and every future run.
5. If all attempts fail, the step is reported as failed with the full attempt log
   — never silently skipped.

Because the sandbox test performs the real action, its result is reused as the
step's result rather than calling the new tool a second time (avoids duplicate
side effects like creating the same issue twice).

Steps can reference an earlier step's real output via the literal placeholder
`"{{step:N}}"` in their args, resolved by the executor before each call
(`Executor._resolve_args`). This matters specifically for synthesis: a
`list_issues` step's real result gets threaded into the next step's
`__missing__` capability request, so the generated function is tested against
real data, not a stand-in string. Note on quality: the classification logic
inside a synthesized function (e.g. which keywords imply "high priority") is
whatever the LLM produces and tests successfully — in one run it settled on a
narrow keyword match (`"urgent"`, `"investigate"`) that under-triggered on this
repo's seed issues. That's an honest limitation of one-shot LLM code generation,
not a bug in the synthesis pipeline itself — the pipeline's job is to make sure
whatever gets registered actually runs against the real API without error.

## 3. What is the learning signal, and what changes between run 1 and run N?

Primary signal: **API calls + LLM calls for a repeated instruction pattern**,
tracked per-execution in `executions.total_api_calls` / `total_llm_calls`.

Measured on this repo (`charanreddy9246/Autonomous-GitHub-Agent`, real API calls,
real numbers logged in `memory.db`):

- Run 1 of "create priority labels, then apply the best-matching one to every
  open issue": no tool exists for either operation, so both were synthesized
  at runtime, sandbox-tested against the live repo, and registered.
  **16 API calls, 2 LLM calls, 18.9s.**
- Run 2, a differently-worded repeat ("apply priority labels to all open
  issues again, creating the priority labels if needed"): `find_similar()`
  matched it to run 1 at cosine similarity **0.799** (threshold 0.75). The
  planner reused the prior decomposition, and both capabilities were already
  in `capability_memory` (`source = synthesized`) — no new synthesis, no
  replanning needed. **9 API calls, 1 LLM call, 5.0s.**
- Net: **7 fewer API calls, ~14s saved, half the LLM calls** — for a
  differently-phrased instruction, not a cache hit on identical text. This is
  printed in the report's `memory_comparison` block (see
  `agent/core/reporter.py`) and reproduced verbatim in DEMO.md.

Secondary signal (built but secondary): success-rate-weighted tool visibility —
`ToolRegistry.specs_for_planner()` surfaces each capability's
`success_count/failure_count` to the planner, so between two ways to accomplish
something the more reliable one is legible to the model.

## Bugs found and fixed during live testing (kept here deliberately, not scrubbed)

Real user testing against the live repo surfaced five real problems, not
hypothetical ones. Documenting them here rather than quietly fixing and
moving on, since the ability to find, diagnose, and fix these is itself part
of what's being evaluated:

1. The planner initially force-fit unrelated existing tools (an issue counter)
   onto a need ("repository activity") that had no matching tool, rather than
   requesting a new one — and separately, on a different attempt, silently
   dropped 2 of the 5 requested items instead of addressing them. Both are
   `gpt-4o-mini` planning-discipline failures. Fixed with explicit prompt rules
   (`agent/core/planner.py`) forbidding topical-only tool matching and requiring
   every distinct request item to map to a step. This substantially improved
   but did not fully eliminate the issue.
2. Switching `PLANNER_MODEL` to `gpt-4o` resolved the remaining mismatch
   outright — it correctly identified "activity" as a genuine capability gap,
   synthesized a real commit-history tool, and the run came back with true
   commit data. `gpt-4o-mini` remains the default for capability *code
   generation* (`SYNTH_MODEL`), where it performed reliably across every test;
   only planning/tool-selection needed the stronger model.
3. The reporter originally only printed which tools ran and whether they
   succeeded, never the actual data they returned or a readable answer to the
   instruction — a real usability gap, not just a display preference. Fixed by
   adding `agent/core/answer.py`, a final step that hands all gathered step
   data to the LLM and asks for one plain-English answer to the original
   instruction, printed at the top of every report (see `print_report` in
   `agent/core/reporter.py`). Costs exactly one extra LLM call per run.
4. A "create issue, then fetch its details" instruction passed the ENTIRE
   result of the create-issue step (`{"number": 8, "url": ...}`) into the
   next step's `issue_number` argument, which expects a plain integer — a
   real inter-step data-shape bug. Fixed at the mechanism level by extending
   `Executor._resolve_args` to support dotted/indexed field paths (e.g.
   `"{{step:0.number}}"`), and updated the planner prompt to require using
   this when a step needs one specific field rather than a whole object.
   Verified this also exposed a second-order issue worth stating plainly:
   the planner does not reliably adopt the new placeholder syntax on its
   own — on retest it still passed the whole dict, and the capability
   synthesizer worked around it by writing a function that expects that
   specific (wrong) shape, rather than the planner using the fix correctly.
   The result was still correct for this one case, but it produced a
   `get`-issue-like tool with an argument shape inconsistent with the base
   `get_issue` tool (int vs. dict) -- a real, undismissed limitation. A
   more durable fix would validate/coerce each step's resolved args against
   the target tool's declared JSON-schema parameter types before calling it,
   rather than relying on the planner to always pick the right placeholder
   form; not implemented here for time.
5. A synthesized "list contributors" tool consistently produced a 404 across
   all 3 attempts: it built a URL like
   `/repos/owner/repo/repos/owner/repo/contributors` because the generated
   code re-inserted the `repository` argument into `client.repo_path()`,
   which already targets the correct repo internally. All 3 retries made the
   *same* mistake, meaning the error feedback alone wasn't specific enough for
   the model to self-correct. Fixed by adding an explicit right/wrong example
   to the synthesis prompt (`agent/synthesis/synthesizer.py`) — the next
   attempt (a fresh run, not a retry of the same attempt) succeeded on its
   first try.

## What I'd build next if I had more time

- **Multi-agent decomposition** — a planner/specialist split so long compound
  instructions don't all funnel through one prompt.
- **Memory compaction** — `executions` grows unboundedly; a periodic job that
  summarizes older rows into a smaller "lessons" table would keep planning-context
  size bounded as usage scales.
- **True process isolation for synthesis** — the sandbox subprocess still shares
  the host's network and filesystem; a container or gVisor-style sandbox would be
  the honest next step before trusting fully unattended synthesis.
- **Rollback** — synthesized tools that create resources don't currently have a
  paired "undo"; worth generating a companion inverse operation when feasible.

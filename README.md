# Autonomous Platform Intelligence Agent (GitHub)

An autonomous GitHub automation agent built to solve a specific engineering challenge: handling complex natural-language instructions when the necessary tools don't exist at design time.
Instead of hardcoding hundreds of GitHub API endpoints, this system starts with just 4 basic tools. When an instruction requires something new (like classifying issue priority or generating triage summaries), it dynamically writes Python code for the missing tool, sandbox-tests it against the live repository in an isolated subprocess, and permanently stores the validated tool in SQLite memory.
See [ARCHITECTURE.md](ARCHITECTURE.md) for the detailed engineering rationale, system design, and live API debugging notes.
## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with:
- `OPENAI_API_KEY` — your OpenAI key
- `GITHUB_TOKEN` — a fine-grained personal access token with **Issues: read/write** on the target repo
- `GITHUB_REPO` — `owner/repo` of a repo you own (writes happen here for real)

Before running the demo, make sure your target GitHub repository has a few sample open issues (without labels) so the instructions have live data to act on. You can create these manually on the GitHub web interface.

## Run

```bash
python -m agent.cli "list all open issues and tell me how many have no labels"
```

Memory persists in `memory.db` (SQLite, gitignored) across runs — do not delete it between demo runs, as the learning loop depends on it.

## Project layout

```
agent/
  cli.py               entrypoint
  github_client.py     authenticated GitHub API wrapper + call counter
  util.py              shared JSON serialization helpers for API data
  core/
    planner.py         LLM decomposition, consults memory before planning
    executor.py        runs steps, partial-failure handling, triggers synthesis
    reporter.py        structured execution audit report
    answer.py          synthesizes human-readable answers from raw step data
  memory/
    db.py                SQLite schema
    execution_memory.py  what the agent has done before
    capability_memory.py what the agent knows how to do
    similarity.py        embeddings + cosine similarity for plan reuse
  synthesis/
    synthesizer.py       LLM generates a new tool, tests it, registers it
    sandbox.py           subprocess-isolated real test against the live repo
  tools/
    github_base.py       deliberately small hardcoded tool set
    registry.py          merges base + synthesized tools
```

# Live Demo Walkthrough Guide

**Target Repository:** `charanreddy9246/Demorepo` (a real GitHub repository with live API calls).

You can test any instruction in the terminal by running:
```bash
python -m agent.cli "<your instruction here>"
```

Here is the exact terminal output from our live presentation proving the 3 core features of the architecture (Base Tools, Tool Synthesis, and Memory Reuse).

---

## 1. Baseline Test (Using Base Tools)

**Instruction:**
```bash
python -m agent.cli "list all the avaibel issues"
```

**What happens:** The agent uses its hardcoded `list_issues` tool to check the repository and retrieves all current open and closed issues. It passes the raw JSON data to the Planner LLM, which summarizes the active issues in a clean, human-readable format.

**Live Output:**
```
======================================================================
INSTRUCTION: list all the avaibel issues
OUTCOME: SUCCESS
1 step(s) succeeded, 0 failed, 0 skipped.
----------------------------------------------------------------------
ANSWER:
There are four issues listed:

1. **Issue 1** - Title: "backend problem" (State: open) - This is affecting the production API and needs urgent attention.
2. **Issue 2** - Title: "error in login page" (State: open) - Users are unable to log in due to an error on the login page. (Label: bug)
3. **Issue 3** - Title: "memory issue" (State: open) - Memory usage increases during execution, causing performance problems.
4. **Issue 4** - Title: "token-verification (safe to close)" (State: closed) - There are no details provided.

The issues that are currently open are issues 1, 2, and 3.
----------------------------------------------------------------------
  [OK] list_issues args={'state': 'all'}
           result: [{'number': 4, 'title': 'token-verification (safe to close)', 'state': 'closed', ...
----------------------------------------------------------------------
COST: 1 API calls | 2 LLM calls | 1.95s
======================================================================
```

---

## 2. Live Capability Synthesis (Inventing New Tools on the Fly)

**Instruction:**
```bash
python -m agent.cli "Close issue number #3."
```

**What happens:** Notice that the agent does not possess a tool to close an issue by default! The Planner detects this missing capability and generates a work order. The Synthesizer dynamically writes Python code at runtime to interact with the GitHub API's closure endpoint, safely verifies the code in an isolated Sandbox, and executes the operation.

**Live Output:**
```
======================================================================
INSTRUCTION: Close issue number #3.
OUTCOME: SUCCESS
1 step(s) succeeded, 0 failed, 0 skipped.
----------------------------------------------------------------------
ANSWER:
Issue number #3 has been successfully closed. You can view it [here](https://github.com/charanreddy9246/Demorepo/issues/3). The issue was titled "memory issue" and was closed by the user `charanreddy9246`.
----------------------------------------------------------------------
  [OK] a_tool_that_can_close_an_issue_in_the_repository args={'issue_number': 3}
           result: {'url': 'https://api.github.com/repos/charanreddy9246/Demorepo/issues/3', ...
           note: capability synthesized at runtime after 1 attempt(s) and registered for reuse
----------------------------------------------------------------------
COST: 1 API calls | 3 LLM calls | 8.39s
======================================================================
```

---

## 3. The Self-Learning Loop (Memory Reuse)

**Instruction:**
```bash
python -m agent.cli "Shut down issue #3."
```

**What happens:** We rephrased the instruction. The agent calculates the cosine similarity of this instruction against its SQLite database memory. It finds a match above the 0.75 threshold (matching the previous run). Instead of synthesizing new code, it loads the previously validated `close_issue` tool directly from the database, executing the operation immediately and cutting execution time dramatically!

**Live Output:**
```
======================================================================
INSTRUCTION: Shut down issue #3.
OUTCOME: SUCCESS
1 step(s) succeeded, 0 failed, 0 skipped.
----------------------------------------------------------------------
ANSWER:
Issue #3, titled "memory issue," has been successfully closed. You can view the details of the closed issue at [this link](https://github.com/charanreddy9246/Demorepo/issues/3). The issue was closed by the owner, charanreddy9246, due to performance problems related to increasing memory usage.
----------------------------------------------------------------------
  [OK] a_tool_that_can_close_an_issue_in_the_repository args={'issue_number': 3}
           result: {'url': 'https://api.github.com/repos/charanreddy9246/Demorepo/issues/3', ...
----------------------------------------------------------------------
COST: 1 API calls | 2 LLM calls | 2.17s
======================================================================
```

### Measurable Learning Proof (Before vs. After):
- **First Run (With Synthesis):** Took **8.39 seconds** and 3 LLM calls.
- **Second Run (Memory Reuse):** Took only **2.17 seconds** and 2 LLM calls.
- **Result:** The memory loop made the exact same operation **almost 4x faster** without requiring any manual retraining!

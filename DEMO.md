# Live Demo Walkthrough Guide

**Target Repository:** `charanreddy9246/Demorepo` (a real GitHub repository with live API calls).

Right now, this repository has 3 real open issues without any labels:
- `backend problem` (#1)
- `login page error` (#2)
- `execution memery issues` (#3)

You can test any instruction in the terminal by running:
```bash
python -m agent.cli "<your instruction here>"
```

Here are the 3 test instructions we use during our live walkthrough to prove the system works:

---

## 1. Baseline Test (Base Tools)
**Command:**
```bash
python -m agent.cli "How many open issues currently have no labels at all?"
```
- **What happens:** Our agent uses its hardcoded `list_issues` tool to check the repository. Since it already knows how to check for labels, it executes cleanly without needing to invent new tools.
- **Result:** Finished in **3.0 seconds** using only **2 API calls**. It accurately reports: *"There are currently 3 open issues that have no labels at all."*

---

## 2. Live Capability Synthesis (Inventing New Tools on the Fly)
**Command:**
```bash
python -m agent.cli "Find all open issues that mention 'login' or 'backend' in the title, and summarize what's broken based on those issues."
```
- **What happens:** Notice that we do not own a tool to filter issues by keyword or summarize text! Our Planner detects this gap and marks them as `__missing__` tools. Our Synthesizer dynamically writes Python code at runtime, launches an isolated background subprocess to safely test the code against our live GitHub repo, and permanently saves the new tools into our SQLite database!
- **Result:** Finished in **13.4 seconds** after writing and verifying two brand new tools. It accurately catches both real issues (`login page error` and `backend problem`) and prints a clean summary from real data!

---

## 3. The Self-Learning Loop (Memory Reuse & Measurable Proof)
**Command:**
```bash
python -m agent.cli "Search the open issues for anything related to login or backend problems and give me a short summary."
```
- **What happens:** Notice that I phrased this command differently than Command 2! Our agent converts this text into an embedding vector and searches our SQLite database using cosine similarity. It matches our previous run with a score of **0.80** (above our 0.75 threshold). It completely bypasses writing new code and directly reuses the tools we saved in Command 2!
- **Measurable Learning Proof (Before vs. After):**
  - **First Run (With Synthesis):** Took **13.4 seconds** and 4 LLM calls.
  - **Second Run (Memory Reuse):** Took only **2.4 seconds** and 2 LLM calls!
  - That is **11 seconds faster** and cuts our LLM calls in half! This gives concrete proof that our SQLite memory loop actively makes the agent faster and cheaper over time without anyone retraining it!

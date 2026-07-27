import os
import sqlite3

DB_PATH = os.environ.get("AGENT_DB_PATH", "memory.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instruction_text TEXT NOT NULL,
    instruction_embedding TEXT,          -- JSON list[float]
    decomposition_json TEXT NOT NULL,    -- planned steps
    steps_result_json TEXT NOT NULL,     -- per-step outcome
    outcome TEXT NOT NULL,               -- success | partial | failed
    total_api_calls INTEGER NOT NULL,
    total_llm_calls INTEGER NOT NULL,
    total_time_s REAL NOT NULL,
    reused_from_execution_id INTEGER,    -- set when planner reused a prior plan
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS capabilities (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    source TEXT NOT NULL,                -- base | synthesized
    code TEXT,                           -- present only for synthesized tools
    parameters_json TEXT,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    constraints_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

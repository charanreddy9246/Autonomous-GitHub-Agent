import json
import sqlite3
from dataclasses import dataclass

from agent.memory import similarity
from agent.memory.db import get_connection

SIMILARITY_THRESHOLD = 0.75


@dataclass
class PastExecution:
    id: int
    instruction_text: str
    decomposition: list
    steps_result: list
    outcome: str
    total_api_calls: int
    total_llm_calls: int
    total_time_s: float
    similarity_score: float


def save_execution(
    instruction_text: str,
    embedding: list[float],
    decomposition: list,
    steps_result: list,
    outcome: str,
    total_api_calls: int,
    total_llm_calls: int,
    total_time_s: float,
    reused_from_execution_id: int | None = None,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO executions
               (instruction_text, instruction_embedding, decomposition_json,
                steps_result_json, outcome, total_api_calls, total_llm_calls,
                total_time_s, reused_from_execution_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                instruction_text,
                similarity.dumps(embedding),
                json.dumps(decomposition),
                json.dumps(steps_result),
                outcome,
                total_api_calls,
                total_llm_calls,
                total_time_s,
                reused_from_execution_id,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def find_similar(embedding: list[float]) -> PastExecution | None:
    """Return the closest successful past execution above the similarity
    threshold, or None if no past execution is close enough to reuse."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM executions WHERE outcome IN ('success', 'partial') "
            "ORDER BY id DESC"
        ).fetchall()
    finally:
        conn.close()

    best = None
    best_score = 0.0
    for row in rows:
        past_embedding = similarity.loads(row["instruction_embedding"])
        score = similarity.cosine_similarity(embedding, past_embedding)
        if score > best_score:
            best_score = score
            best = row

    if best is None or best_score < SIMILARITY_THRESHOLD:
        return None

    return PastExecution(
        id=best["id"],
        instruction_text=best["instruction_text"],
        decomposition=json.loads(best["decomposition_json"]),
        steps_result=json.loads(best["steps_result_json"]),
        outcome=best["outcome"],
        total_api_calls=best["total_api_calls"],
        total_llm_calls=best["total_llm_calls"],
        total_time_s=best["total_time_s"],
        similarity_score=best_score,
    )


def recent(limit: int = 10) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT id, instruction_text, outcome, total_api_calls, "
            "total_llm_calls, total_time_s, reused_from_execution_id, created_at "
            "FROM executions ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()

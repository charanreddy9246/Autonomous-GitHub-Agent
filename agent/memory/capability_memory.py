import json

from agent.memory.db import get_connection


def ensure_base_registered(name: str, description: str, parameters: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO capabilities (name, description, source, parameters_json)
               VALUES (?, ?, 'base', ?)
               ON CONFLICT(name) DO NOTHING""",
            (name, description, json.dumps(parameters)),
        )
        conn.commit()
    finally:
        conn.close()


def register_synthesized(name: str, description: str, code: str, parameters: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO capabilities (name, description, source, code, parameters_json)
               VALUES (?, ?, 'synthesized', ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   description=excluded.description,
                   code=excluded.code,
                   parameters_json=excluded.parameters_json,
                   updated_at=datetime('now')""",
            (name, description, code, json.dumps(parameters)),
        )
        conn.commit()
    finally:
        conn.close()


def record_result(name: str, success: bool) -> None:
    conn = get_connection()
    try:
        col = "success_count" if success else "failure_count"
        conn.execute(
            f"UPDATE capabilities SET {col} = {col} + 1, updated_at=datetime('now') "
            f"WHERE name = ?",
            (name,),
        )
        conn.commit()
    finally:
        conn.close()


def add_constraint(name: str, constraint: str) -> None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT constraints_json FROM capabilities WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return
        constraints = json.loads(row["constraints_json"])
        if constraint not in constraints:
            constraints.append(constraint)
            conn.execute(
                "UPDATE capabilities SET constraints_json = ?, updated_at=datetime('now') "
                "WHERE name = ?",
                (json.dumps(constraints), name),
            )
            conn.commit()
    finally:
        conn.close()


def get_all() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM capabilities").fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        result.append(
            {
                "name": r["name"],
                "description": r["description"],
                "source": r["source"],
                "code": r["code"],
                "parameters": json.loads(r["parameters_json"]) if r["parameters_json"] else {},
                "success_count": r["success_count"],
                "failure_count": r["failure_count"],
                "constraints": json.loads(r["constraints_json"]),
            }
        )
    return result


def get(name: str) -> dict | None:
    for cap in get_all():
        if cap["name"] == name:
            return cap
    return None

# backend/models.py — Thin SQLite helpers for querying persisted data

import sqlite3
from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    con = sqlite3.connect(DATABASE_PATH)
    con.row_factory = sqlite3.Row
    return con


def recent_steps(n: int = 50) -> list[dict]:
    with get_connection() as con:
        rows = con.execute(
            "SELECT * FROM steps ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def total_hallucinations() -> int:
    with get_connection() as con:
        row = con.execute("SELECT COALESCE(SUM(hallucination),0) FROM steps").fetchone()
    return row[0]


def cash_series() -> list[dict]:
    with get_connection() as con:
        rows = con.execute(
            "SELECT step, cash FROM steps ORDER BY step"
        ).fetchall()
    return [dict(r) for r in rows]

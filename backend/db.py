import json
import os
import sqlite3
from contextlib import contextmanager

_DB_PATH = os.environ.get("DB_PATH", "./assignments.db")


@contextmanager
def _conn():
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """Create tables if they don't already exist. Called once at app startup."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS assignments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT    NOT NULL,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                assignment_json TEXT    NOT NULL,
                answer_key_json TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS grading_records (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id   INTEGER NOT NULL REFERENCES assignments(id),
                student_name    TEXT    NOT NULL,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                comments_json   TEXT    NOT NULL,
                final_grade     TEXT    NOT NULL
            );
        """)


def save_assignment(title: str, assignment_data: dict, answer_key_data: dict) -> int:
    """Insert a new assignment row and return the new id."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO assignments (title, assignment_json, answer_key_json) VALUES (?, ?, ?)",
            (title, json.dumps(assignment_data), json.dumps(answer_key_data)),
        )
        return cur.lastrowid


def list_assignments() -> list[dict]:
    """Return all assignments as [{id, title, created_at}], newest first."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, title, created_at FROM assignments ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_assignment(assignment_id: int) -> dict | None:
    """Return the full assignment row including JSON fields, or None if not found."""
    with _conn() as con:
        row = con.execute(
            "SELECT id, title, created_at, assignment_json, answer_key_json "
            "FROM assignments WHERE id = ?",
            (assignment_id,),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["assignment_json"] = json.loads(result["assignment_json"])
    result["answer_key_json"] = json.loads(result["answer_key_json"])
    return result


def save_grading_record(
    assignment_id: int,
    student_name: str,
    comments: list[dict],
    final_grade: str,
) -> int:
    """Insert a grading record and return the new id."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO grading_records "
            "(assignment_id, student_name, comments_json, final_grade) VALUES (?, ?, ?, ?)",
            (assignment_id, student_name, json.dumps(comments), final_grade),
        )
        return cur.lastrowid

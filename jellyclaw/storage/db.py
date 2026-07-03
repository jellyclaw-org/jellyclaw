"""Sqlite storage: the single source of truth for runs, tasks, messages and
agent status. The orchestrator writes here; the CLI and the Phase 2 dashboard
only read. Keep the schema stable — the dashboard depends on it."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal TEXT NOT NULL,
    channel TEXT,
    chat_id TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    agent TEXT NOT NULL,
    role TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'assigned',
    result TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    direction TEXT NOT NULL,
    channel TEXT,
    chat_id TEXT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS agent_status (
    name TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    department TEXT,
    status TEXT NOT NULL DEFAULT 'idle',
    detail TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def state_dir() -> Path:
    """~/.jellyclaw (override with JELLYCLAW_HOME). Holds the db and daemon logs."""
    d = Path(os.environ.get("JELLYCLAW_HOME", Path.home() / ".jellyclaw"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_db_path() -> Path:
    return state_dir() / "jellyclaw.db"


class Database:
    """Thin synchronous sqlite wrapper.

    ponytail: sync sqlite3 called from async code — writes are sub-millisecond
    and single-user, so no aiosqlite/executor needed. Revisit if the dashboard
    ever shows write-contention.
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_db_path()
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")  # readers (dashboard) don't block the writer
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- writes (orchestrator) ------------------------------------------------

    def create_run(self, goal: str, channel: str | None, chat_id: str | None) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (goal, channel, chat_id) VALUES (?, ?, ?)",
            (goal, channel, chat_id),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, status: str, summary: str | None) -> None:
        self.conn.execute(
            "UPDATE runs SET status = ?, summary = ?, completed_at = datetime('now') WHERE id = ?",
            (status, summary, run_id),
        )
        self.conn.commit()

    def create_task(self, run_id: int, agent: str, role: str, description: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO tasks (run_id, agent, role, description) VALUES (?, ?, ?, ?)",
            (run_id, agent, role, description),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_task(self, task_id: int, status: str, result: str | None) -> None:
        self.conn.execute(
            "UPDATE tasks SET status = ?, result = ?, completed_at = datetime('now') WHERE id = ?",
            (status, result, task_id),
        )
        self.conn.commit()

    def log_message(
        self, direction: str, text: str, channel: str | None = None,
        chat_id: str | None = None, run_id: int | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO messages (run_id, direction, channel, chat_id, text) VALUES (?, ?, ?, ?, ?)",
            (run_id, direction, channel, chat_id, text),
        )
        self.conn.commit()

    def set_agent_status(
        self, name: str, role: str, status: str,
        department: str | None = None, detail: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO agent_status (name, role, department, status, detail, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(name) DO UPDATE SET
                 status = excluded.status, detail = excluded.detail,
                 updated_at = excluded.updated_at""",
            (name, role, department, status, detail),
        )
        self.conn.commit()

    # -- reads (CLI, dashboard) -----------------------------------------------

    def recent_runs(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def tasks_for_run(self, run_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def agent_statuses(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM agent_status ORDER BY name").fetchall()
        return [dict(r) for r in rows]

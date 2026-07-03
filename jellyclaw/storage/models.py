"""Record types stored in sqlite. Kept as plain dataclasses mirroring the
tables in db.py — the dashboard and CLI read these, the orchestrator writes
them."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Run:
    id: int
    goal: str
    channel: str | None
    chat_id: str | None
    status: str  # running | completed | failed
    summary: str | None
    created_at: str
    completed_at: str | None


@dataclass
class Task:
    id: int
    run_id: int
    agent: str
    role: str  # ceo | head | worker
    description: str
    status: str  # assigned | running | completed | failed
    result: str | None
    created_at: str
    completed_at: str | None


@dataclass
class Message:
    id: int
    run_id: int | None
    direction: str  # in | out
    channel: str | None
    chat_id: str | None
    text: str
    created_at: str

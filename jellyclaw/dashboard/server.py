"""Phase 2 dashboard: FastAPI app bound to 127.0.0.1 ONLY.

Never bind 0.0.0.0 — there is no auth because there is no network exposure.
Reads the same sqlite db the orchestrator writes (no second source of truth)
and runs a full Orchestrator on a LocalDashboardAdapter so the chat panel
exercises the exact same code path as Telegram.
"""

from __future__ import annotations

import asyncio
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from jellyclaw.channels.local_dashboard_adapter import LocalDashboardAdapter
from jellyclaw.config.schema import JellyClawConfig
from jellyclaw.storage.db import Database

_STATIC = Path(__file__).parent / "static"


def create_app(adapter: LocalDashboardAdapter, db: Database, config: JellyClawConfig) -> FastAPI:
    app = FastAPI(title="JellyClaw dashboard")

    @app.get("/")
    def index():
        return FileResponse(_STATIC / "index.html")

    @app.get("/api/hierarchy")
    def hierarchy():
        statuses = {s["name"]: s for s in db.agent_statuses()}

        def agent(name: str, model: str, role: str) -> dict:
            live = statuses.get(name, {})
            return {
                "name": name, "model": model, "role": role,
                "status": live.get("status", "idle"), "detail": live.get("detail"),
            }

        return {
            "ceo": agent(config.ceo.name, config.ceo.model, "ceo"),
            "departments": [
                {
                    "name": dept.name,
                    "head": agent(dept.head.name or f"{dept.name}-head", dept.head.model, "head"),
                    "workers": [agent(w.name, w.model, "worker") for w in dept.workers],
                }
                for dept in config.departments
            ],
        }

    @app.get("/api/runs")
    def runs():
        result = db.recent_runs()
        for run in result:
            run["tasks"] = db.tasks_for_run(run["id"])
        return result

    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket):
        await websocket.accept()
        adapter.register(websocket)
        try:
            while True:
                await adapter.push(await websocket.receive_text())
        except WebSocketDisconnect:
            adapter.unregister(websocket)

    return app


async def serve_dashboard(config: JellyClawConfig, port: int = 4173, open_browser: bool = True) -> None:
    from jellyclaw.agents.orchestrator import Orchestrator
    from jellyclaw.llm.ollama_client import OllamaClient

    db = Database()
    adapter = LocalDashboardAdapter()
    orchestrator = Orchestrator(config, OllamaClient(), adapter, db)
    server = uvicorn.Server(
        uvicorn.Config(create_app(adapter, db, config),
                       host="127.0.0.1", port=port, log_level="warning")
    )
    if open_browser:
        asyncio.get_event_loop().call_later(
            0.8, webbrowser.open, f"http://127.0.0.1:{port}"
        )
    try:
        await asyncio.gather(server.serve(), orchestrator.run_forever())
    finally:
        db.close()

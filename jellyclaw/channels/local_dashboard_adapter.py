"""Phase 2: channel adapter backing the local dashboard's chat panel.

Same ABC as TelegramAdapter — the orchestrator cannot tell the difference,
which is the point. The dashboard's FastAPI app (dashboard/server.py) feeds
incoming WebSocket text into push() and registers each connected socket so
send_message() can broadcast replies back out.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from jellyclaw.channels.base import ChannelAdapter, IncomingMessage


class LocalDashboardAdapter(ChannelAdapter):
    name = "local"

    def __init__(self) -> None:
        self._queue: asyncio.Queue[IncomingMessage] = asyncio.Queue()
        self._sockets: set = set()  # fastapi WebSocket objects, owned by server.py

    # -- called by dashboard/server.py ---------------------------------------

    def register(self, websocket) -> None:
        self._sockets.add(websocket)

    def unregister(self, websocket) -> None:
        self._sockets.discard(websocket)

    async def push(self, text: str) -> None:
        await self._queue.put(IncomingMessage(chat_id="dashboard", text=text, sender="dashboard"))

    # -- ChannelAdapter interface ---------------------------------------------

    async def send_message(self, chat_id: str, text: str) -> None:
        await self._broadcast({"type": "message", "text": text})

    async def send_status(self, chat_id: str, status: dict) -> None:
        await self._broadcast({"type": "status", "status": status})

    async def listen(self) -> AsyncIterator[IncomingMessage]:
        while True:
            yield await self._queue.get()

    async def start(self) -> None:
        pass  # server lifecycle is owned by uvicorn in the dashboard command

    async def stop(self) -> None:
        pass

    async def _broadcast(self, payload: dict) -> None:
        data = json.dumps(payload)
        for ws in list(self._sockets):
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001 — a dropped tab must not fail the run
                self._sockets.discard(ws)

"""ChannelAdapter: the messaging abstraction.

HARD RULE FOR CONTRIBUTORS: the engine (agents/, cli run loop, storage/) may
only ever import this module — never a concrete adapter. No Telegram (or
Discord, Slack, ...) imports, types, or behavior anywhere outside
channels/<name>_adapter.py. Adding a channel must be a pure addition: one new
adapter file implementing this ABC, one new name in channels/factory.py, one
new `channel:` value in jellyclaw.yaml — zero changes to the engine and zero
risk to existing users' setups. The Phase 2 LocalDashboardAdapter exists
partly as proof this holds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class IncomingMessage:
    chat_id: str  # opaque reply address; only the adapter interprets it
    text: str
    sender: str = ""


class ChannelAdapter(ABC):
    name: str = "channel"  # concrete adapters override; recorded on runs/messages

    @abstractmethod
    async def send_message(self, chat_id: str, text: str) -> None: ...

    @abstractmethod
    async def send_status(self, chat_id: str, status: dict) -> None: ...

    @abstractmethod
    def listen(self) -> AsyncIterator[IncomingMessage]:
        """Async iterator of incoming messages; runs until the adapter stops."""
        ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

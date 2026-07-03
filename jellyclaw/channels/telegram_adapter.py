"""Telegram channel adapter. The ONLY file allowed to import telegram."""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from jellyclaw.channels.base import ChannelAdapter, IncomingMessage

# Telegram message hard limit is 4096 chars.
_MAX_LEN = 4000


class TelegramAdapter(ChannelAdapter):
    name = "telegram"

    def __init__(self, token: str | None = None):
        # Token resolved lazily so the adapter can be constructed (e.g. by
        # `jellyclaw validate` or tests) without credentials.
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._queue: asyncio.Queue[IncomingMessage] = asyncio.Queue()
        self._app: Application | None = None

    async def start(self) -> None:
        if not self._token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not set. Get a token from @BotFather "
                "and export it (or put it in .env)."
            )
        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self) -> None:
        if self._app is None:
            return
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        self._app = None

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.message.text is None:
            return
        await self._queue.put(
            IncomingMessage(
                chat_id=str(update.effective_chat.id),
                text=update.message.text,
                sender=(update.effective_user.username or "") if update.effective_user else "",
            )
        )

    async def send_message(self, chat_id: str, text: str) -> None:
        assert self._app is not None, "adapter not started"
        for i in range(0, len(text) or 1, _MAX_LEN):
            await self._app.bot.send_message(chat_id=chat_id, text=text[i:i + _MAX_LEN] or "(empty)")

    async def send_status(self, chat_id: str, status: dict) -> None:
        await self.send_message(
            chat_id, "\n".join(f"{k}: {v}" for k, v in status.items())
        )

    async def listen(self) -> AsyncIterator[IncomingMessage]:
        while True:
            yield await self._queue.get()

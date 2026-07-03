"""Thin wrapper around the ollama package.

Normalizes replies to a plain dict so agents and tests never depend on the
ollama library's response types:
    {"content": str, "tool_calls": [{"name": str, "arguments": dict}], "raw": <message>}
`raw` is the original message object, appended back to the conversation when
continuing a tool loop.
"""

from __future__ import annotations

import os

import ollama


class OllamaClient:
    def __init__(self, host: str | None = None):
        self._client = ollama.AsyncClient(host=host or os.environ.get("OLLAMA_HOST"))

    async def chat(self, model: str, messages: list, tools: list | None = None) -> dict:
        response = await self._client.chat(model=model, messages=messages, tools=tools or None)
        message = response.message
        tool_calls = [
            {"name": call.function.name, "arguments": dict(call.function.arguments)}
            for call in (message.tool_calls or [])
        ]
        return {"content": message.content or "", "tool_calls": tool_calls, "raw": message}

"""Agent base class: a named role wrapping one Ollama model."""

from __future__ import annotations

import json
import re


class Agent:
    role = "agent"

    def __init__(self, name: str, model: str, llm, system_prompt: str):
        self.name = name
        self.model = model
        self.llm = llm  # anything with async chat(model, messages, tools) -> normalized dict
        self.system_prompt = system_prompt

    async def chat(self, user_content: str, tools: list | None = None) -> dict:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]
        return await self.llm.chat(self.model, messages, tools=tools)


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM reply (models love to wrap
    JSON in prose or code fences). Returns None if nothing parses."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None

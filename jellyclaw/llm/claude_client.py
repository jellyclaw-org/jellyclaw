"""Optional escalation path to the Claude API. OFF by default; only
constructed when jellyclaw.yaml sets escalation.enabled: true and
ANTHROPIC_API_KEY is set.

TODO(vNext): actually wire escalation into the orchestrator (e.g. retry a
failed worker task on Claude). For now this client just works when called.
"""

from __future__ import annotations

import os


class ClaudeClient:
    def __init__(self, model: str = "claude-sonnet-4-6"):
        import anthropic  # imported lazily: only escalation users pay for it

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "escalation.enabled is true but ANTHROPIC_API_KEY is not set"
            )
        self.model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def chat(self, model: str, messages: list, tools: list | None = None) -> dict:
        """Same signature as OllamaClient.chat. `model` argument is ignored in
        favor of the configured escalation model; tools are not supported on
        the escalation path yet (TODO(vNext))."""
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] in ("user", "assistant")]
        kwargs = {"system": system} if system else {}
        response = await self._client.messages.create(
            model=self.model, max_tokens=4096, messages=turns, **kwargs
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return {"content": text, "tool_calls": [], "raw": {"role": "assistant", "content": text}}

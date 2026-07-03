"""OllamaClient normalization, with the ollama package fully mocked."""

from types import SimpleNamespace

from jellyclaw.llm.ollama_client import OllamaClient


class FakeAsyncClient:
    def __init__(self, message, **kwargs):
        self._message = message
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(message=self._message)


def _client_with(message, monkeypatch):
    fake = FakeAsyncClient(message)
    monkeypatch.setattr(
        "jellyclaw.llm.ollama_client.ollama.AsyncClient", lambda host=None: fake
    )
    return OllamaClient(), fake


async def test_plain_reply(monkeypatch):
    message = SimpleNamespace(content="hello", tool_calls=None)
    client, fake = _client_with(message, monkeypatch)
    reply = await client.chat("llama3.1:8b", [{"role": "user", "content": "hi"}])
    assert reply["content"] == "hello"
    assert reply["tool_calls"] == []
    assert reply["raw"] is message
    assert fake.calls[0]["model"] == "llama3.1:8b"
    assert fake.calls[0]["tools"] is None  # no tools passed -> None, not []


async def test_tool_calls_normalized(monkeypatch):
    call = SimpleNamespace(
        function=SimpleNamespace(name="shell", arguments={"command": "ls"})
    )
    message = SimpleNamespace(content="", tool_calls=[call])
    client, _ = _client_with(message, monkeypatch)
    reply = await client.chat("m", [], tools=[{"type": "function"}])
    assert reply["tool_calls"] == [{"name": "shell", "arguments": {"command": "ls"}}]

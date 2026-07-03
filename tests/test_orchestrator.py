"""Delegation flow with a scripted fake LLM and a fake channel — no Ollama
server, no Telegram token."""

import json

from jellyclaw.agents.orchestrator import Orchestrator
from jellyclaw.channels.base import ChannelAdapter, IncomingMessage
from jellyclaw.config.schema import validate_config
from jellyclaw.storage.db import Database


class FakeLLM:
    """Pops scripted replies in order. Each entry is either a content string
    or a full normalized reply dict."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def chat(self, model, messages, tools=None):
        self.calls.append({"model": model, "messages": messages, "tools": tools})
        reply = self.replies.pop(0)
        if isinstance(reply, str):
            reply = {"content": reply, "tool_calls": []}
        reply.setdefault("raw", {"role": "assistant", "content": reply["content"]})
        return reply


class FakeChannel(ChannelAdapter):
    def __init__(self):
        self.sent = []
        self.statuses = []
        self.started = self.stopped = False

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))

    async def send_status(self, chat_id, status):
        self.statuses.append((chat_id, status))

    async def listen(self):
        return
        yield  # empty async iterator; tests call handle_message directly

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


def make_config(tmp_path, tools=None):
    return validate_config({
        "ceo": {"model": "ceo-model", "name": "Boss"},
        "workdir": str(tmp_path / "work"),
        "departments": [{
            "name": "engineering",
            "head": {"model": "head-model"},
            "workers": [{"name": "coder", "model": "worker-model", "tools": tools or []}],
        }],
    })


def make_orchestrator(tmp_path, replies, tools=None):
    llm = FakeLLM(replies)
    channel = FakeChannel()
    db = Database(tmp_path / "test.db")
    orch = Orchestrator(make_config(tmp_path, tools), llm, channel, db)
    return orch, llm, channel, db


async def test_full_delegation_flow(tmp_path):
    orch, llm, channel, db = make_orchestrator(tmp_path, [
        json.dumps({"assignments": [{"department": "engineering", "task": "build it"}]}),
        json.dumps({"assignments": [{"worker": "coder", "task": "write the code"}]}),
        "I wrote the code.",          # worker
        "Engineering built it.",      # head review
        "Done: we built it.",         # ceo summary
    ])
    await orch.handle_message(IncomingMessage(chat_id="42", text="build me a thing"))

    assert channel.sent == [("42", "Done: we built it.")]
    assert channel.statuses[0][1]["delegating_to"] == "engineering"
    assert llm.replies == []  # every scripted call consumed, in order
    # correct model per layer
    assert [c["model"] for c in llm.calls] == [
        "ceo-model", "head-model", "worker-model", "head-model", "ceo-model"
    ]

    runs = db.recent_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "completed"
    assert runs[0]["summary"] == "Done: we built it."
    tasks = db.tasks_for_run(runs[0]["id"])
    assert [t["role"] for t in tasks] == ["ceo", "head", "worker"]
    assert all(t["status"] == "completed" for t in tasks)
    assert all(s["status"] == "idle" for s in db.agent_statuses())


async def test_worker_uses_tool(tmp_path):
    orch, llm, channel, db = make_orchestrator(tmp_path, [
        json.dumps({"assignments": [{"department": "engineering", "task": "save a note"}]}),
        json.dumps({"assignments": [{"worker": "coder", "task": "write note.txt"}]}),
        {"content": "", "tool_calls": [{"name": "file_ops", "arguments":
            {"operation": "write", "path": "note.txt", "content": "hello"}}]},
        "Wrote note.txt.",            # worker after tool result
        "Done by engineering.",       # head review
        "All done.",                  # ceo summary
    ], tools=["file_ops"])
    await orch.handle_message(IncomingMessage(chat_id="1", text="save a note"))

    assert (tmp_path / "work" / "note.txt").read_text() == "hello"
    assert channel.sent == [("1", "All done.")]
    # tool result was fed back to the worker on its second call
    tool_msgs = [m for m in llm.calls[3]["messages"] if m.get("role") == "tool"]
    assert len(tool_msgs) == 1 and "5 chars" in tool_msgs[0]["content"]


async def test_unparseable_plan_falls_back_to_first_department(tmp_path):
    orch, llm, channel, db = make_orchestrator(tmp_path, [
        "sure, I'll get right on that!",  # CEO returns no JSON
        json.dumps({"assignments": [{"worker": "coder", "task": "do the goal"}]}),
        "did it", "report", "final",
    ])
    await orch.handle_message(IncomingMessage(chat_id="1", text="the goal"))
    assert channel.sent == [("1", "final")]
    # the fallback assigned the raw goal to engineering's head
    assert "the goal" in llm.calls[1]["messages"][1]["content"]


async def test_failed_run_reports_and_recovers(tmp_path):
    class ExplodingLLM:
        async def chat(self, model, messages, tools=None):
            raise RuntimeError("ollama is down")

    channel = FakeChannel()
    db = Database(tmp_path / "test.db")
    orch = Orchestrator(make_config(tmp_path), ExplodingLLM(), channel, db)
    await orch.handle_message(IncomingMessage(chat_id="7", text="goal"))

    assert db.recent_runs()[0]["status"] == "failed"
    assert "ollama is down" in channel.sent[0][1]
    # agents were reset to idle so the next run starts clean
    assert all(s["status"] == "idle" for s in db.agent_statuses())

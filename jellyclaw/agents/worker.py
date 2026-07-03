"""WorkerAgent: executes one task, optionally calling its allowed tools in a
loop, and returns a text result."""

from __future__ import annotations

from jellyclaw.agents.base import Agent
from jellyclaw.tools import registry

_SYSTEM = """You are {name}, a worker in the {department} department of a
small AI company. You complete tasks assigned by your department head.
{tool_line}
When you are done, reply with a plain-text summary of what you did and the
result."""

MAX_TOOL_ROUNDS = 8


class WorkerAgent(Agent):
    role = "worker"

    def __init__(self, name: str, department: str, model: str, llm, tools: list[str]):
        self.department = department
        self.tools = tools
        tool_line = (
            f"You can use these tools: {', '.join(tools)}." if tools
            else "You have no tools; answer from reasoning alone."
        )
        super().__init__(
            name, model, llm,
            _SYSTEM.format(name=name, department=department, tool_line=tool_line),
        )

    async def execute(self, task: str) -> str:
        tool_schemas = registry.schemas_for(self.tools) if self.tools else None
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task},
        ]
        # ponytail: bounded sequential tool loop; MAX_TOOL_ROUNDS keeps a
        # confused local model from spinning forever.
        for _ in range(MAX_TOOL_ROUNDS):
            reply = await self.llm.chat(self.model, messages, tools=tool_schemas)
            if not reply["tool_calls"]:
                return reply["content"]
            messages.append(reply["raw"])
            for call in reply["tool_calls"]:
                result = await registry.call(call["name"], call["arguments"])
                messages.append(
                    {"role": "tool", "content": result, "tool_name": call["name"]}
                )
        return f"Stopped after {MAX_TOOL_ROUNDS} tool rounds without a final answer."

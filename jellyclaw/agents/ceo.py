"""CEOAgent: turns a user goal into per-department assignments, and writes
the final summary once departments report back."""

from __future__ import annotations

from jellyclaw.agents.base import Agent, extract_json

_SYSTEM = """You are {name}, the CEO of a small AI company. You receive goals
from the owner and delegate them to your departments: {departments}.
Be concise and decisive."""

_PLAN_PROMPT = """Goal from the owner:
{goal}

Split this goal into one task per department that should be involved.
Respond with ONLY a JSON object in this exact shape:
{{"assignments": [{{"department": "<department name>", "task": "<what that department must do>"}}]}}
Only use these department names: {departments}."""

_SUMMARY_PROMPT = """The goal was:
{goal}

Department reports:
{reports}

Write a short final report to the owner: what was done, key results, and
anything that failed. Plain text, no JSON."""


class CEOAgent(Agent):
    role = "ceo"

    def __init__(self, name: str, model: str, llm, department_names: list[str]):
        self.department_names = department_names
        super().__init__(
            name, model, llm,
            _SYSTEM.format(name=name, departments=", ".join(department_names)),
        )

    async def plan(self, goal: str) -> list[dict]:
        """Returns [{"department": ..., "task": ...}]."""
        reply = await self.chat(
            _PLAN_PROMPT.format(goal=goal, departments=", ".join(self.department_names))
        )
        parsed = extract_json(reply["content"])
        assignments = []
        if parsed:
            for item in parsed.get("assignments", []):
                if item.get("department") in self.department_names and item.get("task"):
                    assignments.append({"department": item["department"], "task": item["task"]})
        if not assignments:
            # Model didn't produce usable JSON — degrade gracefully rather than
            # fail the run. TODO(vNext): retry the plan call once with the
            # parse error fed back to the model.
            assignments = [{"department": self.department_names[0], "task": goal}]
        return assignments

    async def summarize(self, goal: str, reports: dict[str, str]) -> str:
        text = "\n\n".join(f"[{dept}]\n{report}" for dept, report in reports.items())
        reply = await self.chat(_SUMMARY_PROMPT.format(goal=goal, reports=text))
        return reply["content"]

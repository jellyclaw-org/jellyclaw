"""DepartmentHeadAgent: breaks a department task into worker tasks, then
reviews/summarizes what the workers produced."""

from __future__ import annotations

from jellyclaw.agents.base import Agent, extract_json

_SYSTEM = """You are the head of the {department} department in a small AI
company. Your team: {workers}. You break tasks into assignments for your
team and review their work. Be concise."""

_ASSIGN_PROMPT = """Task from the CEO:
{task}

Break it into one assignment per worker that should be involved.
Respond with ONLY a JSON object in this exact shape:
{{"assignments": [{{"worker": "<worker name>", "task": "<what that worker must do>"}}]}}
Only use these worker names: {workers}."""

_REVIEW_PROMPT = """The department task was:
{task}

Worker results:
{results}

Write a short report for the CEO: what your department accomplished, key
output, and any problems. Plain text, no JSON."""


class DepartmentHeadAgent(Agent):
    role = "head"

    def __init__(self, name: str, department: str, model: str, llm, worker_names: list[str]):
        self.department = department
        self.worker_names = worker_names
        super().__init__(
            name, model, llm,
            _SYSTEM.format(department=department, workers=", ".join(worker_names)),
        )

    async def assign(self, task: str) -> list[dict]:
        """Returns [{"worker": ..., "task": ...}]."""
        reply = await self.chat(
            _ASSIGN_PROMPT.format(task=task, workers=", ".join(self.worker_names))
        )
        parsed = extract_json(reply["content"])
        assignments = []
        if parsed:
            for item in parsed.get("assignments", []):
                if item.get("worker") in self.worker_names and item.get("task"):
                    assignments.append({"worker": item["worker"], "task": item["task"]})
        if not assignments:
            # Same graceful fallback as CEOAgent.plan.
            assignments = [{"worker": self.worker_names[0], "task": task}]
        return assignments

    async def review(self, task: str, results: dict[str, str]) -> str:
        text = "\n\n".join(f"[{worker}]\n{result}" for worker, result in results.items())
        reply = await self.chat(_REVIEW_PROMPT.format(task=task, results=text))
        return reply["content"]

"""Orchestrator: wires CEO -> department heads -> workers and runs the loop.

Depends only on the ChannelAdapter ABC — never on a concrete channel. That is
what lets `jellyclaw run` (Telegram) and `jellyclaw dashboard` (local
WebSocket) share this exact code path.
"""

from __future__ import annotations

import logging

from jellyclaw.agents.ceo import CEOAgent
from jellyclaw.agents.department_head import DepartmentHeadAgent
from jellyclaw.agents.worker import WorkerAgent
from jellyclaw.channels.base import ChannelAdapter, IncomingMessage
from jellyclaw.config.schema import JellyClawConfig
from jellyclaw.storage.db import Database
from jellyclaw.tools.builtin import file_ops

log = logging.getLogger("jellyclaw")


class Orchestrator:
    def __init__(self, config: JellyClawConfig, llm, channel: ChannelAdapter, db: Database):
        self.config = config
        self.channel = channel
        self.db = db
        file_ops.set_workdir(config.workdir)

        dept_names = [d.name for d in config.departments]
        self.ceo = CEOAgent(config.ceo.name, config.ceo.model, llm, dept_names)
        self.heads: dict[str, DepartmentHeadAgent] = {}
        self.workers: dict[str, dict[str, WorkerAgent]] = {}
        for dept in config.departments:
            head_name = dept.head.name or f"{dept.name}-head"
            worker_names = [w.name for w in dept.workers]
            self.heads[dept.name] = DepartmentHeadAgent(
                head_name, dept.name, dept.head.model, llm, worker_names
            )
            self.workers[dept.name] = {
                w.name: WorkerAgent(w.name, dept.name, w.model, llm, w.tools)
                for w in dept.workers
            }

        # TODO(vNext): wire ClaudeClient in as an escalation path when
        # config.escalation.enabled — see llm/claude_client.py.

        self._register_agents()

    def _register_agents(self) -> None:
        self.db.set_agent_status(self.ceo.name, "ceo", "idle")
        for dept_name, head in self.heads.items():
            self.db.set_agent_status(head.name, "head", "idle", department=dept_name)
            for worker in self.workers[dept_name].values():
                self.db.set_agent_status(worker.name, "worker", "idle", department=dept_name)

    async def run_forever(self) -> None:
        """Start the channel and process messages until cancelled."""
        await self.channel.start()
        try:
            # ponytail: messages handled one at a time. TODO(vNext): concurrent
            # runs per chat, parallel worker execution, retries.
            async for message in self.channel.listen():
                await self.handle_message(message)
        finally:
            await self.channel.stop()

    async def handle_message(self, message: IncomingMessage) -> None:
        chat_id = message.chat_id
        self.db.log_message("in", message.text, channel=self.channel.name, chat_id=chat_id)
        run_id = self.db.create_run(message.text, self.channel.name, chat_id)
        try:
            summary = await self._execute_run(run_id, message.text, chat_id)
            self.db.finish_run(run_id, "completed", summary)
            await self._send(chat_id, summary, run_id)
        except Exception as exc:  # noqa: BLE001 — one bad run must not kill the loop
            log.exception("run %s failed", run_id)
            self.db.finish_run(run_id, "failed", str(exc))
            self._register_agents()  # reset any agent stuck in 'working'
            await self._send(chat_id, f"Run failed: {exc}", run_id)

    async def _execute_run(self, run_id: int, goal: str, chat_id: str) -> str:
        # 1. CEO plans.
        self.db.set_agent_status(self.ceo.name, "ceo", "working", detail="planning")
        ceo_task = self.db.create_task(run_id, self.ceo.name, "ceo", f"Plan: {goal}")
        plan = await self.ceo.plan(goal)
        self.db.finish_task(ceo_task, "completed", str(plan))
        await self.channel.send_status(
            chat_id,
            {"run": run_id, "stage": "planned",
             "delegating_to": ", ".join(a["department"] for a in plan)},
        )

        # 2-4. Each department: head assigns, workers execute, head reviews.
        reports: dict[str, str] = {}
        for assignment in plan:
            dept = assignment["department"]
            head = self.heads[dept]

            self.db.set_agent_status(head.name, "head", "working", department=dept, detail="assigning")
            head_task = self.db.create_task(run_id, head.name, "head", assignment["task"])
            worker_plan = await head.assign(assignment["task"])

            results: dict[str, str] = {}
            for wa in worker_plan:
                worker = self.workers[dept][wa["worker"]]
                self.db.set_agent_status(worker.name, "worker", "working",
                                         department=dept, detail=wa["task"][:120])
                worker_task = self.db.create_task(run_id, worker.name, "worker", wa["task"])
                try:
                    result = await worker.execute(wa["task"])
                    self.db.finish_task(worker_task, "completed", result)
                except Exception as exc:  # noqa: BLE001
                    result = f"worker failed: {exc}"
                    self.db.finish_task(worker_task, "failed", str(exc))
                results[worker.name] = result
                self.db.set_agent_status(worker.name, "worker", "idle", department=dept)

            report = await head.review(assignment["task"], results)
            self.db.finish_task(head_task, "completed", report)
            self.db.set_agent_status(head.name, "head", "idle", department=dept)
            reports[dept] = report

        # 5. CEO summarizes for the user.
        summary = await self.ceo.summarize(goal, reports)
        self.db.set_agent_status(self.ceo.name, "ceo", "idle")
        return summary

    async def _send(self, chat_id: str, text: str, run_id: int) -> None:
        self.db.log_message("out", text, channel=self.channel.name,
                            chat_id=chat_id, run_id=run_id)
        await self.channel.send_message(chat_id, text)

"""Builtin `shell` tool.

SECURITY TRADEOFF: worker agents run local LLM output as commands. We reduce
(not eliminate) the blast radius by: (1) an allowlist of first-word commands,
(2) no shell interpretation — the command is shlex-split and exec'd directly,
so pipes/redirects/`;` don't work, (3) a hard timeout. This is a convenience
guardrail for a single-user local tool, not a sandbox: `python -c` alone can
do anything. Users who add models they don't trust should remove `shell` from
their workers' tools.
TODO(vNext): make the allowlist configurable in jellyclaw.yaml.
"""

from __future__ import annotations

import asyncio
import shlex

from jellyclaw.tools import registry

ALLOWED_COMMANDS = {
    "ls", "cat", "head", "tail", "grep", "find", "wc", "echo", "pwd",
    "date", "which", "uname", "git", "python", "python3", "uv",
}
TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 4000


@registry.register(
    "shell",
    "Run a shell command (no pipes/redirects; allowlisted commands only) and return its output.",
    {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "The command to run"}},
        "required": ["command"],
    },
)
async def shell(command: str) -> str:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"could not parse command: {exc}"
    if not argv:
        return "empty command"
    if argv[0] not in ALLOWED_COMMANDS:
        return (
            f"command '{argv[0]}' is not allowed. "
            f"Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}"
        )
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        return f"command timed out after {TIMEOUT_SECONDS}s"
    output = stdout.decode(errors="replace")
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
    return f"exit code {proc.returncode}\n{output}"

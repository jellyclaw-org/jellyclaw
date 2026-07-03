"""Builtin `file_ops` tool: read/write files confined to the configured
working directory (jellyclaw.yaml `workdir`). Paths that resolve outside the
workdir are rejected — no traversal via `..` or symlinks."""

from __future__ import annotations

from pathlib import Path

from jellyclaw.tools import registry

_workdir = Path.cwd()
MAX_READ_CHARS = 8000


def set_workdir(path: str | Path) -> None:
    """Called once by the orchestrator at startup, from config."""
    global _workdir
    _workdir = Path(path).resolve()
    _workdir.mkdir(parents=True, exist_ok=True)


def _resolve(relative_path: str) -> Path:
    target = (_workdir / relative_path).resolve()
    if not target.is_relative_to(_workdir):
        raise ValueError(f"path '{relative_path}' escapes the working directory")
    return target


@registry.register(
    "file_ops",
    "Read or write a text file inside the working directory.",
    {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["read", "write"]},
            "path": {"type": "string", "description": "Path relative to the working directory"},
            "content": {"type": "string", "description": "Content to write (write only)"},
        },
        "required": ["operation", "path"],
    },
)
async def file_ops(operation: str, path: str, content: str = "") -> str:
    target = _resolve(path)
    if operation == "read":
        if not target.exists():
            return f"file not found: {path}"
        text = target.read_text(errors="replace")
        if len(text) > MAX_READ_CHARS:
            text = text[:MAX_READ_CHARS] + "\n... (truncated)"
        return text
    if operation == "write":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"wrote {len(content)} chars to {path}"
    return f"unknown operation '{operation}' (use read or write)"

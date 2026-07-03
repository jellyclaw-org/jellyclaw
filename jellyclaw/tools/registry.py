"""Tool registry: name -> (async function + JSON schema).

Adding a tool = one register() call in a new module under builtin/, plus
importing that module in tools/__init__.py. Nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema for the arguments object
    func: Callable[..., Awaitable[str]]


_REGISTRY: dict[str, Tool] = {}


def register(name: str, description: str, parameters: dict):
    def decorator(func: Callable[..., Awaitable[str]]):
        _REGISTRY[name] = Tool(name, description, parameters, func)
        return func

    return decorator


def get(name: str) -> Tool:
    if name not in _REGISTRY:
        raise KeyError(f"unknown tool '{name}' (available: {', '.join(sorted(_REGISTRY))})")
    return _REGISTRY[name]


def schemas_for(names: list[str]) -> list[dict]:
    """Ollama tool-call format for the given tool names."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in (get(n) for n in names)
    ]


async def call(name: str, arguments: dict[str, Any]) -> str:
    """Invoke a tool; tool errors become a string result the model can read
    and react to, instead of crashing the worker."""
    try:
        return await get(name).func(**arguments)
    except Exception as exc:  # noqa: BLE001 — model-facing, must not crash the run
        return f"tool error: {exc}"

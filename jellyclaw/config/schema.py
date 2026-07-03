"""Pydantic models for jellyclaw.yaml — the primary UX surface of the tool.

Validation errors are reformatted into human paths like
"departments[0].workers[1].model is required" (see format_errors) because
this file is hand-edited by new users.

Note: `channel` is deliberately a plain string, not a Literal — adding a new
channel (e.g. discord) must only require a new adapter file and a new value
here, with zero schema changes. The channel factory rejects unknown names
with a clear error.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

KNOWN_TOOLS = {"shell", "file_ops"}


class WorkerConfig(BaseModel):
    name: str
    model: str
    tools: list[str] = Field(default_factory=list)


class HeadConfig(BaseModel):
    model: str
    name: str | None = None


class DepartmentConfig(BaseModel):
    name: str
    head: HeadConfig
    workers: list[WorkerConfig] = Field(min_length=1)


class CEOConfig(BaseModel):
    model: str
    name: str = "CEO"


class EscalationConfig(BaseModel):
    enabled: bool = False
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"


class JellyClawConfig(BaseModel):
    channel: str = "telegram"
    ceo: CEOConfig
    departments: list[DepartmentConfig] = Field(min_length=1)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
    # Working directory the file_ops tool is confined to.
    workdir: str = "."


class ConfigError(Exception):
    """Raised with a human-readable, already-formatted message."""


def format_errors(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        path = ""
        for part in err["loc"]:
            path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else str(part))
        if err["type"] == "missing":
            lines.append(f"{path} is required")
        else:
            lines.append(f"{path}: {err['msg']}")
    return "\n".join(lines)


def validate_config(data: dict) -> JellyClawConfig:
    if not isinstance(data, dict):
        raise ConfigError("jellyclaw.yaml must be a YAML mapping (key: value pairs)")
    try:
        config = JellyClawConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(format_errors(exc)) from exc

    # Unknown tool names fail here, not at runtime mid-task.
    for d_i, dept in enumerate(config.departments):
        for w_i, worker in enumerate(dept.workers):
            for tool in worker.tools:
                if tool not in KNOWN_TOOLS:
                    raise ConfigError(
                        f"departments[{d_i}].workers[{w_i}].tools: unknown tool "
                        f"'{tool}' (available: {', '.join(sorted(KNOWN_TOOLS))})"
                    )
    return config

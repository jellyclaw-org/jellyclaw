"""Linux systemd user service: install/stop/status for `jellyclaw run`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from jellyclaw.storage.db import state_dir

UNIT = "jellyclaw.service"
_FORWARD_ENV = ("TELEGRAM_BOT_TOKEN", "OLLAMA_HOST", "ANTHROPIC_API_KEY", "JELLYCLAW_HOME")


def _unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / UNIT


def log_path() -> Path:
    logs = state_dir() / "logs"
    logs.mkdir(exist_ok=True)
    return logs / "jellyclaw.log"


def install(workdir: Path) -> str:
    env_lines = "\n".join(
        f'Environment="{k}={v}"' for k in _FORWARD_ENV if (v := os.environ.get(k))
    )
    unit = f"""[Unit]
Description=JellyClaw agent orchestrator
After=network.target

[Service]
ExecStart={sys.executable} -m jellyclaw run
WorkingDirectory={workdir}
Restart=on-failure
RestartSec=5
StandardOutput=append:{log_path()}
StandardError=append:{log_path()}
{env_lines}

[Install]
WantedBy=default.target
"""
    path = _unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", UNIT], check=True)
    return (
        f"Installed systemd user service {UNIT} ({path})\nLogs: {log_path()}\n"
        "Tip: run `loginctl enable-linger $USER` so it survives logout."
    )


def stop() -> str:
    if not _unit_path().exists():
        return "No jellyclaw systemd service is installed."
    subprocess.run(["systemctl", "--user", "disable", "--now", UNIT], capture_output=True)
    return f"Stopped and disabled {UNIT}. Re-enable with `jellyclaw daemon install`."


def status() -> str:
    if not _unit_path().exists():
        return "not installed"
    result = subprocess.run(
        ["systemctl", "--user", "is-active", UNIT], capture_output=True, text=True
    )
    return result.stdout.strip() or "unknown"

"""macOS launchd user agent: install/stop/status for `jellyclaw run`."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from jellyclaw.storage.db import state_dir

LABEL = "in.jellyclaw.agent"

# Env vars the service needs but launchd won't inherit from your shell.
_FORWARD_ENV = ("TELEGRAM_BOT_TOKEN", "OLLAMA_HOST", "ANTHROPIC_API_KEY", "JELLYCLAW_HOME")


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def log_path() -> Path:
    logs = state_dir() / "logs"
    logs.mkdir(exist_ok=True)
    return logs / "jellyclaw.log"


def install(workdir: Path) -> str:
    env = {k: v for k in _FORWARD_ENV if (v := os.environ.get(k))}
    plist = {
        "Label": LABEL,
        # sys.executable -m jellyclaw: works no matter how jellyclaw was installed.
        "ProgramArguments": [sys.executable, "-m", "jellyclaw", "run"],
        "WorkingDirectory": str(workdir),
        "KeepAlive": {"SuccessfulExit": False},  # restart on failure only
        "RunAtLoad": True,
        "StandardOutPath": str(log_path()),
        "StandardErrorPath": str(log_path()),
    }
    if env:
        plist["EnvironmentVariables"] = env
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
    path.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "load", "-w", str(path)], check=True)
    return f"Installed launchd agent {LABEL} ({path})\nLogs: {log_path()}"


def stop() -> str:
    path = _plist_path()
    if not path.exists():
        return "No jellyclaw launchd agent is installed."
    subprocess.run(["launchctl", "unload", "-w", str(path)], capture_output=True)
    return f"Stopped and disabled {LABEL}. (Plist kept at {path}; re-enable with `jellyclaw daemon install`.)"


def status() -> str:
    if not _plist_path().exists():
        return "not installed"
    result = subprocess.run(["launchctl", "list", LABEL], capture_output=True, text=True)
    if result.returncode != 0:
        return "installed but not loaded"
    for line in result.stdout.splitlines():
        if '"PID"' in line:
            return f"running (pid {line.split('=')[1].strip(' ;')})"
    return "loaded (not currently running)"

"""JellyClaw CLI: init / validate / run / doctor / daemon / dashboard."""

from __future__ import annotations

import asyncio
import importlib.resources
import logging
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

import typer

from jellyclaw.config.loader import DEFAULT_CONFIG_PATH, load_config
from jellyclaw.config.schema import ConfigError, JellyClawConfig

app = typer.Typer(help="JellyClaw: your own local AI company, run from one YAML file.")
daemon_app = typer.Typer(help="Run JellyClaw as a background service (24/7).")
app.add_typer(daemon_app, name="daemon")

TEMPLATES = ("dev-team", "sales-office")


def _load_dotenv() -> None:
    """Tiny .env loader — not worth a dependency. Existing env wins."""
    env_file = Path(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _load_config_or_exit() -> JellyClawConfig:
    try:
        return load_config()
    except ConfigError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(1)


@app.command()
def init(
    template: str = typer.Option(
        "dev-team", help=f"Starter template: {', '.join(TEMPLATES)}"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing jellyclaw.yaml"),
):
    """Create ./jellyclaw.yaml from a starter template."""
    if template not in TEMPLATES:
        typer.secho(f"Unknown template '{template}'. Available: {', '.join(TEMPLATES)}", fg="red")
        raise typer.Exit(1)
    if DEFAULT_CONFIG_PATH.exists() and not force:
        typer.secho("jellyclaw.yaml already exists (use --force to overwrite).", fg="yellow")
        raise typer.Exit(1)
    content = (
        importlib.resources.files("jellyclaw") / "templates" / f"{template}.yaml"
    ).read_text()
    DEFAULT_CONFIG_PATH.write_text(content)
    typer.secho(f"Created jellyclaw.yaml from the {template} template.\n", fg="green")
    typer.echo(
        "Next steps:\n"
        "  1. Make sure Ollama is running and has the models pulled\n"
        "     (e.g. `ollama pull llama3.1:8b`)\n"
        "  2. Create a Telegram bot with @BotFather and export the token:\n"
        "     export TELEGRAM_BOT_TOKEN=...   (or put it in a .env file)\n"
        "  3. Check everything: jellyclaw doctor\n"
        "  4. Start it: jellyclaw run"
    )


@app.command()
def validate():
    """Validate jellyclaw.yaml and print the hierarchy it describes."""
    config = _load_config_or_exit()
    typer.secho("jellyclaw.yaml is valid.\n", fg="green")
    typer.echo(f"channel: {config.channel}")
    typer.echo(f"{config.ceo.name} (CEO, {config.ceo.model})")
    for dept in config.departments:
        head_name = dept.head.name or f"{dept.name}-head"
        typer.echo(f"└─ {dept.name}: {head_name} (head, {dept.head.model})")
        for worker in dept.workers:
            tools = f" tools: {', '.join(worker.tools)}" if worker.tools else ""
            typer.echo(f"   └─ {worker.name} ({worker.model}){tools}")
    if config.escalation.enabled:
        typer.echo(f"escalation: {config.escalation.provider} / {config.escalation.model}")


async def _run_orchestrator(config: JellyClawConfig, channel) -> None:
    from jellyclaw.agents.orchestrator import Orchestrator
    from jellyclaw.llm.ollama_client import OllamaClient
    from jellyclaw.storage.db import Database

    db = Database()
    orchestrator = Orchestrator(config, OllamaClient(), channel, db)
    try:
        await orchestrator.run_forever()
    finally:
        db.close()


@app.command()
def run():
    """Start the orchestrator in the foreground (Ctrl+C to stop)."""
    _load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = _load_config_or_exit()
    from jellyclaw.channels.factory import create_channel

    try:
        channel = create_channel(config.channel)
    except ValueError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(f"JellyClaw running (channel: {config.channel}). Ctrl+C to stop.")
    try:
        asyncio.run(_run_orchestrator(config, channel))
    except KeyboardInterrupt:
        typer.echo("\nShutting down.")
    except RuntimeError as exc:  # e.g. missing TELEGRAM_BOT_TOKEN at start()
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(1)


@app.command()
def doctor():
    """Check Ollama, Telegram token, config, and daemon status."""
    _load_dotenv()
    failures = 0

    def report(ok: bool, name: str, detail: str) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        typer.secho(f"  {'✓' if ok else '✗'} {name}: {detail}", fg="green" if ok else "red")

    typer.echo("JellyClaw doctor\n")

    # Config
    config = None
    try:
        config = load_config()
        report(True, "config", "jellyclaw.yaml is valid")
    except ConfigError as exc:
        report(False, "config", str(exc).replace("\n", "; "))

    # Ollama
    async def _check_ollama() -> str:
        import ollama

        response = await asyncio.wait_for(ollama.AsyncClient(
            host=os.environ.get("OLLAMA_HOST")).list(), timeout=5)
        return f"reachable ({len(response.models)} models available)"

    try:
        detail = asyncio.run(_check_ollama())
        report(True, "ollama", detail)
    except Exception as exc:  # noqa: BLE001
        report(False, "ollama", f"not reachable ({exc}) — is `ollama serve` running?")

    # Telegram token (only meaningful if channel is telegram)
    if config is None or config.channel == "telegram":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            report(False, "telegram", "TELEGRAM_BOT_TOKEN is not set")
        elif re.fullmatch(r"\d+:[\w-]{30,}", token):
            report(True, "telegram", "TELEGRAM_BOT_TOKEN is set and looks valid")
        else:
            report(False, "telegram", "TELEGRAM_BOT_TOKEN is set but doesn't look like a bot token")

    # Daemon
    report(True, "daemon", _daemon_status_text())

    typer.echo("")
    if failures:
        typer.secho(f"{failures} check(s) failed.", fg="red")
        raise typer.Exit(1)
    typer.secho("All checks passed.", fg="green")


# -- daemon ---------------------------------------------------------------


def _daemon_module():
    if sys.platform == "darwin":
        from jellyclaw.daemon import launchd

        return launchd
    if sys.platform.startswith("linux"):
        from jellyclaw.daemon import systemd

        return systemd
    return None


def _daemon_status_text() -> str:
    module = _daemon_module()
    return module.status() if module else f"not supported on {platform.system()}"


def _require_daemon_module():
    module = _daemon_module()
    if module is None:
        typer.secho(
            "Background service support on Windows is planned but not yet "
            "available. Use `jellyclaw run` in a terminal for now.",
            fg="yellow",
        )
        raise typer.Exit(1)
    return module


@daemon_app.command("install")
def daemon_install():
    """Register jellyclaw as a background service (starts now, survives reboot)."""
    _load_dotenv()  # so the token gets baked into the service environment
    _load_config_or_exit()  # fail fast: don't install a service that can't start
    module = _require_daemon_module()
    typer.echo(module.install(Path.cwd()))


@daemon_app.command("stop")
def daemon_stop():
    """Stop and disable the background service."""
    typer.echo(_require_daemon_module().stop())


@daemon_app.command("status")
def daemon_status():
    """Show background service status."""
    typer.echo(_daemon_status_text())


@daemon_app.command("logs")
def daemon_logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Keep tailing the log"),
    lines: int = typer.Option(50, "--lines", "-n"),
):
    """Show the background service log."""
    module = _require_daemon_module()
    path = module.log_path()
    if not path.exists():
        typer.echo(f"No log file yet at {path}.")
        raise typer.Exit(0)
    if follow:
        subprocess.run(["tail", "-n", str(lines), "-f", str(path)])
    else:
        text = path.read_text(errors="replace").splitlines()
        typer.echo("\n".join(text[-lines:]))


# -- dashboard (Phase 2) ----------------------------------------------------


@app.command()
def dashboard(
    port: int = typer.Option(4173, help="Port on 127.0.0.1"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open the browser"),
):
    """Start the local dashboard (hierarchy view, chat with the CEO, history)."""
    _load_dotenv()
    config = _load_config_or_exit()
    from jellyclaw.dashboard.server import serve_dashboard

    typer.echo(f"Dashboard on http://127.0.0.1:{port} (Ctrl+C to stop)")
    try:
        asyncio.run(serve_dashboard(config, port=port, open_browser=not no_browser))
    except KeyboardInterrupt:
        typer.echo("\nShutting down.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

# JellyClaw

Your own AI company, running on your machine.

JellyClaw runs a hierarchy of AI agents — a **CEO**, **department heads**, and
**workers** — on your own hardware via [Ollama](https://ollama.com), configured
with a single YAML file. Send the CEO a goal from Telegram (or the local
dashboard); it delegates to department heads, who assign tasks to workers,
who execute with tools and report back up the chain. You get the final report
in your chat. Everything stays local. https://jellyclaw.in

## Install

Zero-install with [uv](https://docs.astral.sh/uv/):

```sh
uvx jellyclaw init
uvx jellyclaw run
```

Or the classic way:

```sh
pip install jellyclaw
```

Requires Python 3.11+ and a running Ollama.

## Quick start

```sh
# 1. Create a config from the dev-team template
uvx jellyclaw init

# 2. Pull the models it uses
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b

# 3. Create a bot with @BotFather on Telegram, then
export TELEGRAM_BOT_TOKEN=123456:ABC...   # or put it in a .env file

# 4. Check everything is wired up
uvx jellyclaw doctor

# 5. Go
uvx jellyclaw run
```

Message your bot on Telegram with a goal ("research competitors for X and
write a summary to notes.md") and watch your company work.

## Commands

| Command | What it does |
|---|---|
| `jellyclaw init [--template dev-team\|sales-office]` | Create `./jellyclaw.yaml` from a template |
| `jellyclaw validate` | Validate the config and print the hierarchy |
| `jellyclaw run` | Run the orchestrator in the foreground |
| `jellyclaw doctor` | Pass/fail checklist: config, Ollama, Telegram token, daemon |
| `jellyclaw daemon install\|stop\|status\|logs` | Run 24/7 as a background service (macOS launchd / Linux systemd; Windows planned) |
| `jellyclaw dashboard` | Local web dashboard on 127.0.0.1:4173 — live hierarchy, chat with the CEO, run history |

## YAML schema

```yaml
channel: telegram        # messaging channel: telegram | local (dashboard)

ceo:
  model: llama3.1:8b     # required — any Ollama model tag
  name: "The Boss"       # optional, default "CEO"

departments:             # at least one
  - name: engineering
    head:
      model: llama3.1:8b # required
      name: eng-lead     # optional, default "<department>-head"
    workers:             # at least one per department
      - name: coder
        model: qwen2.5-coder:7b
        tools: [shell, file_ops]   # optional; available: shell, file_ops

workdir: .               # directory the file_ops tool is confined to

escalation:              # optional, off by default
  enabled: false         # true -> allow escalating to the Claude API
  provider: anthropic
  model: claude-sonnet-4-6
```

Environment variables (see `.env.example`; a `.env` file in the working
directory is loaded automatically): `TELEGRAM_BOT_TOKEN`, `OLLAMA_HOST`
(default `http://127.0.0.1:11434`), `ANTHROPIC_API_KEY` (escalation only).

State (sqlite history + daemon logs) lives in `~/.jellyclaw/`.

### Tools

- **shell** — runs a command with an allowlist (`ls`, `git`, `python`, …),
  no pipes/redirects, 30s timeout. It is a guardrail, not a sandbox — only
  give it to workers running models you trust.
- **file_ops** — read/write text files, confined to `workdir` (no path
  traversal).

### Channels

The engine only knows the `ChannelAdapter` interface (`channels/base.py`).
Telegram and the local dashboard are the two current adapters; adding another
(Discord is planned) is one new adapter file plus one line in
`channels/factory.py` — no engine changes.

## Development

```sh
git clone https://github.com/JellyClaw-org/jellyclaw
cd jellyclaw
uv sync
uv run pytest
```

Tests mock Ollama and Telegram — no server or token needed.

### Manual verification checklist

1. `uv sync` succeeds and `uv run pytest` passes.
2. `uv run jellyclaw init` creates `jellyclaw.yaml` and prints next steps.
3. `uv run jellyclaw validate` prints the hierarchy for the template.
4. `uv run jellyclaw doctor` correctly reports pass/fail per check
   (try with and without `TELEGRAM_BOT_TOKEN` set and Ollama running).
5. With a real bot token and Ollama models pulled: `uv run jellyclaw run`,
   message the bot a goal, and confirm a plan status + final report come back.
6. `uv run jellyclaw daemon install` registers the service (macOS or Linux),
   `daemon status` shows it running, `daemon logs` shows output,
   `daemon stop` stops it.
7. `uv run jellyclaw dashboard` opens http://127.0.0.1:4173 showing the
   hierarchy; a message sent from the chat panel reaches the CEO through the
   same orchestrator path as Telegram, and the run appears in the history
   table.

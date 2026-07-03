"""channel name (from jellyclaw.yaml) -> ChannelAdapter instance.

To add a channel: write channels/<name>_adapter.py implementing
ChannelAdapter, add one entry here. Nothing else in the codebase changes.
"""

from __future__ import annotations

from jellyclaw.channels.base import ChannelAdapter


def create_channel(name: str) -> ChannelAdapter:
    # Imports are inside the branches so users only load (and only need
    # working deps for) the channel they configured.
    if name == "telegram":
        from jellyclaw.channels.telegram_adapter import TelegramAdapter

        return TelegramAdapter()
    if name == "local":
        from jellyclaw.channels.local_dashboard_adapter import LocalDashboardAdapter

        return LocalDashboardAdapter()
    raise ValueError(
        f"unknown channel '{name}' in jellyclaw.yaml (available: telegram, local)"
    )

import pytest

from jellyclaw.channels.factory import create_channel
from jellyclaw.channels.local_dashboard_adapter import LocalDashboardAdapter
from jellyclaw.channels.telegram_adapter import TelegramAdapter


def test_telegram():
    assert isinstance(create_channel("telegram"), TelegramAdapter)


def test_local():
    assert isinstance(create_channel("local"), LocalDashboardAdapter)


def test_unknown_channel():
    with pytest.raises(ValueError) as exc:
        create_channel("discord")
    assert "discord" in str(exc.value)
    assert "telegram" in str(exc.value)  # tells the user what IS available

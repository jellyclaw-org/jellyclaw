import pytest

from jellyclaw.config.schema import ConfigError, validate_config

VALID = {
    "channel": "telegram",
    "ceo": {"model": "llama3.1:8b", "name": "The Boss"},
    "departments": [
        {
            "name": "engineering",
            "head": {"model": "llama3.1:8b"},
            "workers": [
                {"name": "coder", "model": "qwen2.5-coder:7b", "tools": ["shell", "file_ops"]},
                {"name": "reviewer", "model": "llama3.1:8b", "tools": ["file_ops"]},
            ],
        }
    ],
    "escalation": {"enabled": False},
}


def test_valid_config():
    config = validate_config(VALID)
    assert config.channel == "telegram"
    assert config.ceo.name == "The Boss"
    assert config.departments[0].workers[0].tools == ["shell", "file_ops"]
    assert config.escalation.enabled is False
    assert config.workdir == "."


def test_missing_worker_model_gives_human_path():
    data = {
        "ceo": {"model": "m"},
        "departments": [
            {"name": "eng", "head": {"model": "m"},
             "workers": [{"name": "a", "model": "m"}, {"name": "b"}]}
        ],
    }
    with pytest.raises(ConfigError) as exc:
        validate_config(data)
    assert "departments[0].workers[1].model is required" in str(exc.value)


def test_missing_ceo():
    with pytest.raises(ConfigError) as exc:
        validate_config({"departments": VALID["departments"]})
    assert "ceo is required" in str(exc.value)


def test_unknown_tool_rejected():
    data = {
        "ceo": {"model": "m"},
        "departments": [
            {"name": "eng", "head": {"model": "m"},
             "workers": [{"name": "a", "model": "m", "tools": ["browser"]}]}
        ],
    }
    with pytest.raises(ConfigError) as exc:
        validate_config(data)
    assert "unknown tool 'browser'" in str(exc.value)
    assert "departments[0].workers[0]" in str(exc.value)


def test_not_a_mapping():
    with pytest.raises(ConfigError):
        validate_config(["not", "a", "dict"])


def test_defaults():
    config = validate_config(
        {"ceo": {"model": "m"},
         "departments": [{"name": "d", "head": {"model": "m"},
                          "workers": [{"name": "w", "model": "m"}]}]}
    )
    assert config.channel == "telegram"
    assert config.ceo.name == "CEO"
    assert config.escalation.enabled is False

"""Load and validate a jellyclaw.yaml file."""

from __future__ import annotations

from pathlib import Path

import yaml

from jellyclaw.config.schema import ConfigError, JellyClawConfig, validate_config

DEFAULT_CONFIG_PATH = Path("jellyclaw.yaml")


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> JellyClawConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"{path} not found. Run `jellyclaw init` to create one from a template."
        )
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    return validate_config(data)

"""Persistent user configuration for QR65 lighting behavior."""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .theme import parse_rgb, read_requested_color

CONFIG_VERSION = 1
DEFAULT_STATIC_COLOR = "#7DAEA3"
MAX_CONFIG_SIZE = 64 * 1024


@dataclass(frozen=True)
class Config:
    """Validated version-one QR65 configuration."""

    version: int = CONFIG_VERSION
    mode: str = "dynamic"
    static_color: str = DEFAULT_STATIC_COLOR
    brightness: int | None = None
    color_matching: bool = False


def config_file() -> Path:
    """Return the XDG configuration path."""
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "edifier-qr65" / "config.toml"


def _validate(config: Config) -> Config:
    if type(config.version) is not int or config.version != CONFIG_VERSION:
        raise ValueError(f"config version must be {CONFIG_VERSION}")
    if not isinstance(config.mode, str) or config.mode not in ("dynamic", "static"):
        raise ValueError('config mode must be "dynamic" or "static"')
    if not isinstance(config.static_color, str):
        raise ValueError("config static_color must use #RRGGBB format")
    parse_rgb(config.static_color)
    if config.brightness is not None and (
        type(config.brightness) is not int or not 0 <= config.brightness <= 100
    ):
        raise ValueError("config brightness must be between 0 and 100")
    if type(config.color_matching) is not bool:
        raise ValueError("config color_matching must be true or false")
    return Config(
        config.version,
        config.mode,
        config.static_color.strip().upper(),
        config.brightness,
        config.color_matching,
    )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="ascii", dir=path.parent, prefix=f".{path.name}-", delete=False
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def save_config(config: Config) -> Config:
    """Validate and atomically persist configuration."""
    config = _validate(config)
    lines = [
        f"version = {config.version}",
        f'mode = "{config.mode}"',
        f'static_color = "{config.static_color}"',
        f"color_matching = {'true' if config.color_matching else 'false'}",
    ]
    if config.brightness is not None:
        lines.append(f"brightness = {config.brightness}")
    _atomic_write(config_file(), "\n".join(lines) + "\n")
    return config


def _initial_static_color() -> str:
    try:
        color = read_requested_color()
        return DEFAULT_STATIC_COLOR if color is None else "#%02X%02X%02X" % color
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return DEFAULT_STATIC_COLOR


def load_config() -> Config:
    """Read validated configuration, migrating the legacy color on first use."""
    path = config_file()
    try:
        if path.stat().st_size > MAX_CONFIG_SIZE:
            raise ValueError("config file is too large")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return save_config(Config(static_color=_initial_static_color()))
    except tomllib.TOMLDecodeError as error:
        raise ValueError("config file is malformed") from error
    except UnicodeError as error:
        raise ValueError("config file is not valid UTF-8") from error

    try:
        config = Config(
            version=data["version"],
            mode=data["mode"],
            static_color=data["static_color"],
            brightness=data.get("brightness"),
            color_matching=data.get("color_matching", False),
        )
    except (KeyError, TypeError) as error:
        raise ValueError("config file is missing required values") from error
    return _validate(config)

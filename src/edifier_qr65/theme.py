"""Omarchy accent-color state shared by the hook and daemon."""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator

RGB_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}\Z")
REQUEST_VERSION = 1
MAX_REQUEST_SIZE = 64 * 1024


def state_file() -> Path:
    """Return the XDG state file containing the latest requested color."""
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return root / "edifier-qr65" / "color"


def request_file() -> Path:
    """Return the authoritative desired-color document path."""
    return state_file().with_name("request.json")


def lock_file() -> Path:
    """Return the advisory lock shared by all queued CLI operations."""
    return state_file().with_name("operation.lock")


def ownership_lock_file() -> Path:
    """Return the lock that serializes live BLE controller ownership."""
    return state_file().with_name("ble.lock")


def parse_rgb(value: str) -> tuple[int, int, int]:
    """Parse a strict CSS-style six-digit RGB value."""
    value = value.strip()
    if not RGB_PATTERN.fullmatch(value):
        raise ValueError("color must use #RRGGBB format")
    red, green, blue = bytes.fromhex(value[1:])
    return red, green, blue


def read_requested_color() -> tuple[int, int, int] | None:
    """Read the authoritative request, falling back only to legacy state."""
    request = read_request()
    return None if request is None else parse_rgb(request.color)


@dataclass(frozen=True)
class Request:
    """One validated desired-color request."""

    color: str
    source: str
    updated_at: int


def _read_legacy_request() -> Request | None:
    path = state_file()
    try:
        if path.stat().st_size > 64:
            raise ValueError("legacy color file is too large")
        color = path.read_text(encoding="ascii").strip().upper()
        parse_rgb(color)
        return Request(color, "", int(path.stat().st_mtime))
    except FileNotFoundError:
        return None


def read_request() -> Request | None:
    """Read request.json, using plain color only when request.json is absent."""
    path = request_file()
    try:
        if path.stat().st_size > MAX_REQUEST_SIZE:
            raise ValueError("request file is too large")
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _read_legacy_request()
    except json.JSONDecodeError as error:
        raise ValueError("request file is malformed") from error
    except UnicodeError as error:
        raise ValueError("request file is not valid UTF-8") from error
    if not isinstance(data, dict):
        raise ValueError("request file root must be an object")
    if type(data.get("version")) is not int or data["version"] != REQUEST_VERSION:
        raise ValueError(f"request version must be {REQUEST_VERSION}")
    color = data.get("color")
    source = data.get("source")
    updated_at = data.get("updatedAt")
    if not isinstance(color, str):
        raise ValueError("request color must use #RRGGBB format")
    parse_rgb(color)
    if not isinstance(source, str) or not source:
        raise ValueError("request source must be a non-empty string")
    if type(updated_at) is not int:
        raise ValueError("request updatedAt must be an integer")
    return Request(color.strip().upper(), source, updated_at)


def _atomic_write(path: Path, content: str, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="ascii", dir=path.parent, prefix=prefix, delete=False
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@contextmanager
def operation_lock() -> Iterator[None]:
    """Serialize configuration and desired-color operations across processes."""
    path = lock_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@contextmanager
def ownership_lock(*, blocking: bool = True) -> Iterator[None]:
    """Hold exclusive ownership while a process can access QR65 GATT."""
    path = ownership_lock_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(lock, flags)
        except BlockingIOError as error:
            raise RuntimeError("QR65 BLE control is already owned") from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _request_color(value: str, source: str = "direct") -> tuple[int, int, int]:
    color = parse_rgb(value)
    if not isinstance(source, str) or not source:
        raise ValueError("request source must be a non-empty string")
    normalized = value.strip().upper()
    try:
        previous = read_request()
    except (OSError, UnicodeError, ValueError):
        previous = None
    updated_at = max(
        int(time.time()),
        0 if previous is None else previous.updated_at + 1,
    )
    metadata = {
        "version": REQUEST_VERSION,
        "color": normalized,
        "source": source,
        "updatedAt": updated_at,
    }
    _atomic_write(request_file(), json.dumps(metadata, separators=(",", ":")) + "\n", ".request-")
    # Keep the old daemon operational; new readers never prefer this mirror.
    _atomic_write(state_file(), normalized + "\n", ".color-")
    return color


def request_color(value: str, source: str = "direct") -> tuple[int, int, int]:
    """Persist one desired color under the shared operation lock."""
    with operation_lock():
        return _request_color(value, source)


@dataclass(frozen=True)
class SyncResult:
    """Outcome of resolving and optionally queueing a desired color."""

    color: str
    source: str
    queued: bool = True


def _resolve_accent() -> str:
    result = subprocess.run(
        ["omarchy", "theme", "color", "accent"], check=True, capture_output=True,
        text=True, timeout=3,
    )
    accent = result.stdout.strip()
    parse_rgb(accent)
    return accent.upper()


def _sync_desired(theme_hook: bool = False) -> SyncResult:
    from .config import load_config

    config = load_config()
    if config.mode == "static":
        if theme_hook:
            return SyncResult(config.static_color, "static", queued=False)
        _request_color(config.static_color, "static")
        return SyncResult(config.static_color, "static")

    try:
        accent = _resolve_accent()
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        parse_rgb(config.static_color)
        _request_color(config.static_color, "static-fallback")
        return SyncResult(config.static_color, "static-fallback")
    _request_color(accent, "theme-accent")
    return SyncResult(accent, "theme-accent")


def sync_desired(*, theme_hook: bool = False) -> SyncResult:
    """Atomically select and queue the configured desired color."""
    with operation_lock():
        return _sync_desired(theme_hook)


def set_dynamic_mode() -> SyncResult:
    """Persist dynamic mode and queue its resolved request without interleaving."""
    from .config import load_config, save_config

    with operation_lock():
        config = load_config()
        save_config(replace(config, mode="dynamic"))
        return _sync_desired()


def set_static_mode(value: str) -> str:
    """Persist static mode and queue its color without interleaving."""
    from .config import load_config, save_config

    parse_rgb(value)
    normalized = value.strip().upper()
    with operation_lock():
        save_config(replace(load_config(), mode="static", static_color=normalized))
        _request_color(normalized, "static")
    return normalized


def set_brightness(value: int) -> int:
    """Persist desired LED brightness for the daemon to apply."""
    from .config import load_config, save_config

    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError("brightness must be between 0 and 100")
    with operation_lock():
        save_config(replace(load_config(), brightness=value))
    return value


def set_color_matching(enabled: bool) -> bool:
    """Enable or disable the built-in QR65 color-matching profile."""
    from .config import load_config, save_config

    if type(enabled) is not bool:
        raise ValueError("color matching state must be boolean")
    with operation_lock():
        save_config(replace(load_config(), color_matching=enabled))
    return enabled


def sync_omarchy_accent() -> str:
    """Compatibility entry point used by the installed Omarchy theme hook."""
    return sync_desired(theme_hook=True).color

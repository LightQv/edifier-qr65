"""Daemon runtime status and stable CLI status composition."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .ble import QR65_SERVICE_UUIDS
from .config import Config
from .desired import parse_rgb, read_request, state_file

STATUS_VERSION = 1
STATUS_STALE_SECONDS = 60
STATUS_FUTURE_SKEW_SECONDS = 5
MAX_STATUS_SIZE = 64 * 1024
MAX_MESSAGE_SIZE = 2048
CONNECTION_STATES = {
    "starting", "scanning", "activation-required", "connecting", "connected", "released", "error"
}


def status_file() -> Path:
    """Return the XDG daemon status path."""
    return state_file().with_name("status.json")


def write_runtime_status(
    connection: str,
    applied_color: str | None = None,
    message: str = "",
    *,
    applied_brightness: int | None = None,
    now: float | None = None,
) -> None:
    """Validate and atomically write one daemon heartbeat."""
    if connection not in CONNECTION_STATES:
        raise ValueError("invalid connection state")
    if not isinstance(message, str) or len(message) > MAX_MESSAGE_SIZE:
        raise ValueError(f"message must be at most {MAX_MESSAGE_SIZE} characters")
    if applied_color is not None:
        parse_rgb(applied_color)
        applied_color = applied_color.upper()
    if applied_brightness is not None and (
        type(applied_brightness) is not int or not 0 <= applied_brightness <= 100
    ):
        raise ValueError("applied brightness must be between 0 and 100")
    payload = {
        "version": STATUS_VERSION,
        "connection": connection,
        "appliedColor": applied_color,
        "appliedBrightness": applied_brightness,
        "message": message,
        "updatedAt": int(time.time() if now is None else now),
    }
    path = status_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".status-", delete=False
        ) as temporary:
            json.dump(payload, temporary, separators=(",", ":"))
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _read_json(path: Path, maximum: int) -> dict[str, Any]:
    with path.open("rb") as source:
        raw = source.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("file is too large")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root is not an object")
    return value


def _legacy_connected_status(current: int) -> dict[str, Any] | None:
    """Detect the pre-status daemon's held connection without touching BLE."""
    try:
        result = subprocess.run(
            ["/usr/bin/bluetoothctl", "devices", "Connected"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    addresses = [
        parts[1]
        for line in result.stdout.splitlines()
        if len(parts := line.split(maxsplit=2)) >= 2 and parts[0] == "Device"
    ]
    for address in addresses:
        try:
            info = subprocess.run(
                ["/usr/bin/bluetoothctl", "info", address],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        details = info.stdout.lower()
        if "connected: yes" in details and any(uuid in details for uuid in QR65_SERVICE_UUIDS):
            break
    else:
        return None
    return {
        "connection": "connected",
        "appliedColor": None,
        "appliedBrightness": None,
        "message": "Connected; detailed status starts after the next daemon restart",
        "updatedAt": current,
    }


def read_runtime_status(
    *, now: float | None = None, allow_legacy_connection: bool = False
) -> dict[str, Any]:
    """Read runtime state, mapping unavailable or stale data to a safe error."""
    current = int(time.time() if now is None else now)
    try:
        data = _read_json(status_file(), MAX_STATUS_SIZE)
    except FileNotFoundError:
        if allow_legacy_connection and (legacy := _legacy_connected_status(current)):
            return legacy
        return {"connection": "error", "appliedColor": None, "appliedBrightness": None,
                "message": "Daemon status unavailable", "updatedAt": 0}
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {"connection": "error", "appliedColor": None, "appliedBrightness": None,
                "message": "Daemon status unavailable", "updatedAt": 0}
    try:
        if type(data.get("version")) is not int or data["version"] != STATUS_VERSION:
            raise ValueError("unsupported status version")
        connection = data["connection"]
        applied = data["appliedColor"]
        brightness = data.get("appliedBrightness")
        message = data["message"]
        updated = data["updatedAt"]
        if (not isinstance(connection, str) or connection not in CONNECTION_STATES
                or not isinstance(message, str)
                or len(message) > MAX_MESSAGE_SIZE):
            raise ValueError("invalid runtime status")
        if type(updated) is not int:
            raise ValueError("invalid update time")
        if applied is not None:
            if not isinstance(applied, str):
                raise ValueError("invalid applied color")
            parse_rgb(applied)
            applied = applied.upper()
        if brightness is not None and (
            type(brightness) is not int or not 0 <= brightness <= 100
        ):
            raise ValueError("invalid applied brightness")
    except (KeyError, ValueError):
        return {"connection": "error", "appliedColor": None, "appliedBrightness": None,
                "message": "Daemon status unavailable", "updatedAt": 0}
    if updated > current + STATUS_FUTURE_SKEW_SECONDS:
        return {"connection": "error", "appliedColor": applied, "appliedBrightness": brightness,
                "message": "Daemon status timestamp is in the future", "updatedAt": updated}
    if connection != "released" and current - updated > STATUS_STALE_SECONDS:
        return {"connection": "error", "appliedColor": applied, "appliedBrightness": brightness,
                "message": "Daemon status is stale", "updatedAt": updated}
    return {"connection": connection, "appliedColor": applied, "appliedBrightness": brightness,
            "message": message, "updatedAt": updated}


def _read_request() -> tuple[str | None, str]:
    try:
        request = read_request()
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return None, ""
    return (None, "") if request is None else (request.color, request.source)


def build_status(config: Config, *, now: float | None = None) -> dict[str, Any]:
    """Combine persistent desired state with daemon-reported runtime state."""
    requested, source = _read_request()
    runtime = read_runtime_status(now=now, allow_legacy_connection=True)
    return {
        "version": STATUS_VERSION,
        "mode": config.mode,
        "configuredStaticColor": config.static_color,
        "configuredBrightness": config.brightness,
        "colorMatching": config.color_matching,
        "requestedColor": requested,
        "requestedSource": source,
        "appliedColor": runtime["appliedColor"],
        "appliedBrightness": runtime["appliedBrightness"],
        "connection": runtime["connection"],
        "message": runtime["message"],
        "updatedAt": runtime["updatedAt"],
    }

import json
import subprocess

import pytest

from edifier_qr65.config import Config
from edifier_qr65.status import (
    MAX_STATUS_SIZE,
    STATUS_FUTURE_SKEW_SECONDS,
    STATUS_STALE_SECONDS,
    build_status,
    read_runtime_status,
    status_file,
    write_runtime_status,
)
from edifier_qr65.desired import request_color


def test_runtime_status_write_is_atomic(xdg_dirs) -> None:
    write_runtime_status("connected", "#12abcd", now=100)
    assert json.loads(status_file().read_text()) == {
        "version": 1, "connection": "connected", "appliedColor": "#12ABCD",
        "appliedBrightness": None, "message": "", "updatedAt": 100,
    }
    assert not list(status_file().parent.glob(".status-*"))


def test_ephemeral_status_does_not_force_storage_sync(xdg_dirs, monkeypatch) -> None:
    monkeypatch.setattr(
        "edifier_qr65.status.os.fsync",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not fsync status")),
    )

    write_runtime_status("connected", "#123456")

    assert read_runtime_status()["appliedColor"] == "#123456"


def test_status_combines_stable_camel_case_fields(xdg_dirs) -> None:
    request_color("#89B4FA", "dynamic")
    write_runtime_status("connected", "#89B4FA", now=100)
    assert build_status(Config(), now=100) == {
        "version": 1, "mode": "dynamic", "configuredStaticColor": "#7DAEA3",
        "configuredBrightness": None, "colorMatching": False,
        "requestedColor": "#89B4FA", "requestedSource": "dynamic",
        "appliedColor": "#89B4FA", "appliedBrightness": None,
        "connection": "connected", "message": "",
        "updatedAt": 100,
    }


def test_stale_connected_status_becomes_error(xdg_dirs) -> None:
    write_runtime_status("connected", "#FFFFFF", now=100)
    result = read_runtime_status(now=100 + STATUS_STALE_SECONDS + 1)
    assert result["connection"] == "error"
    assert result["appliedColor"] == "#FFFFFF"
    assert result["message"] == "Daemon status is stale"


def test_released_status_does_not_expire(xdg_dirs) -> None:
    write_runtime_status(
        "released", "#FFFFFF", applied_brightness=40, now=100
    )
    result = read_runtime_status(now=100 + STATUS_STALE_SECONDS + 1)
    assert result["connection"] == "released"
    assert result["appliedBrightness"] == 40


def test_old_v1_status_without_brightness_remains_valid(xdg_dirs) -> None:
    status_file().parent.mkdir(parents=True)
    status_file().write_text(
        '{"version":1,"connection":"connected","appliedColor":"#FFFFFF",'
        '"message":"","updatedAt":100}\n'
    )
    result = read_runtime_status(now=100)
    assert result["connection"] == "connected"
    assert result["appliedBrightness"] is None


def test_future_runtime_timestamp_is_rejected(xdg_dirs) -> None:
    write_runtime_status(
        "connected", "#FFFFFF", now=100 + STATUS_FUTURE_SKEW_SECONDS + 1
    )

    result = read_runtime_status(now=100)

    assert result["connection"] == "error"
    assert result["message"] == "Daemon status timestamp is in the future"


@pytest.mark.parametrize("content", [b"not json", b"[]", b'{"version":2}'])
def test_malformed_runtime_status_is_unavailable(xdg_dirs, content: bytes) -> None:
    status_file().parent.mkdir(parents=True)
    status_file().write_bytes(content)
    assert read_runtime_status(now=100)["message"] == "Daemon status unavailable"


def test_oversized_runtime_status_is_unavailable(xdg_dirs) -> None:
    status_file().parent.mkdir(parents=True)
    status_file().write_bytes(b" " * (MAX_STATUS_SIZE + 1))
    assert read_runtime_status()["connection"] == "error"


def test_runtime_status_rejects_invalid_values_without_replacing_file(xdg_dirs) -> None:
    write_runtime_status("starting", now=100)
    original = status_file().read_bytes()
    with pytest.raises(ValueError):
        write_runtime_status("connected", "bad", now=101)
    with pytest.raises(ValueError):
        write_runtime_status("connected", applied_brightness=101, now=101)
    with pytest.raises(ValueError):
        write_runtime_status("connected", applied_brightness=True, now=101)
    assert status_file().read_bytes() == original


def test_composed_status_detects_legacy_daemon_connection(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        if command[1] == "devices":
            return subprocess.CompletedProcess(
                [], 0, stdout="Device AA:BB:CC:DD:EE:FF unrelated-name\n", stderr=""
            )
        return subprocess.CompletedProcess(
            [], 0,
            stdout=("Connected: yes\nUUID: Vendor specific "
                    "(48095d01-1a48-11e9-ab14-d663bd873d93)\n"),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", run)

    result = build_status(Config(), now=100)

    assert result["connection"] == "connected"
    assert result["appliedColor"] is None
    assert result["updatedAt"] == 100
    assert "next daemon restart" in result["message"]
    assert calls == [
        ["/usr/bin/bluetoothctl", "devices", "Connected"],
        ["/usr/bin/bluetoothctl", "info", "AA:BB:CC:DD:EE:FF"],
    ]


def test_legacy_name_without_qr65_service_is_not_connected(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(command, **_kwargs):
        output = (
            "Device AA:BB:CC:DD:EE:FF EDIFIER BLE\n"
            if command[1] == "devices"
            else "Connected: yes\nUUID: Audio Sink (0000110b-0000-1000-8000-00805f9b34fb)\n"
        )
        return subprocess.CompletedProcess([], 0, stdout=output, stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    assert build_status(Config(), now=100)["connection"] == "error"


@pytest.mark.parametrize("kind", ["stale", "malformed", "unsupported"])
def test_versioned_status_never_uses_legacy_fallback(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    status_file().parent.mkdir(parents=True)
    if kind == "stale":
        write_runtime_status("connected", now=1)
    elif kind == "malformed":
        status_file().write_text("not json")
    else:
        status_file().write_text('{"version":2}')

    def unexpected(*_args, **_kwargs):
        raise AssertionError("legacy detection must only run when status.json is missing")

    monkeypatch.setattr(subprocess, "run", unexpected)
    result = build_status(Config(), now=100)

    assert result["connection"] == "error"
    assert result["message"] in {"Daemon status is stale", "Daemon status unavailable"}


def test_runtime_status_rejects_oversized_message(xdg_dirs) -> None:
    with pytest.raises(ValueError, match="at most 2048"):
        write_runtime_status("error", message="x" * 2049)


def test_boolean_status_version_is_rejected(xdg_dirs) -> None:
    status_file().parent.mkdir(parents=True)
    status_file().write_text(
        '{"version":true,"connection":"connected","appliedColor":null,'
        '"message":"","updatedAt":100}'
    )
    assert read_runtime_status(now=100)["connection"] == "error"


def test_unhashable_connection_is_rejected(xdg_dirs) -> None:
    status_file().parent.mkdir(parents=True)
    status_file().write_text(
        '{"version":1,"connection":[],"appliedColor":null,'
        '"message":"","updatedAt":100}'
    )
    assert read_runtime_status(now=100)["connection"] == "error"

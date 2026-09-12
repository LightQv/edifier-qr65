import json
import math
import os
import subprocess
import sys
from pathlib import Path

from edifier_qr65.cli import main
from edifier_qr65.config import Config, config_file, load_config, save_config
from edifier_qr65.status import read_runtime_status, write_runtime_status
from edifier_qr65.desired import ownership_lock, read_requested_color, request_color


def test_device_cannot_bypass_direct_write_gate(xdg_dirs, capsys) -> None:
    assert main(["set-color", "#123456", "--device", "AA:BB"]) == 1
    assert capsys.readouterr().err == "error: --device and --delay require --direct\n"


def test_hidden_delay_cannot_bypass_direct_write_gate(xdg_dirs, capsys) -> None:
    assert main(["set-color", "#123456", "--delay", "1"]) == 1
    assert capsys.readouterr().err == "error: --device and --delay require --direct\n"


def test_direct_write_rejects_invalid_timeout(xdg_dirs, capsys) -> None:
    assert main(["set-color", "#123456", "--direct", "--timeout", "nan"]) == 1
    assert capsys.readouterr().err == "error: timeout must be a finite positive number\n"


def test_direct_write_rejects_active_daemon(xdg_dirs, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
    )
    assert main(["set-color", "#123456", "--direct"]) == 1
    assert capsys.readouterr().err == (
        "error: stop or release the QR65 daemon before using --direct\n"
    )


def test_scan_rejects_invalid_timeout(capsys) -> None:
    assert main(["scan", "--timeout", str(math.inf)]) == 1
    assert capsys.readouterr().err == "error: timeout must be a finite positive number\n"


def test_inspect_refuses_when_daemon_owns_ble(xdg_dirs, capsys) -> None:
    with ownership_lock():
        assert main(["inspect", "--device", "AA:BB"]) == 1
    assert capsys.readouterr().err == "error: QR65 BLE control is already owned\n"


def test_mode_static_persists_and_queues(xdg_dirs, capsys) -> None:
    assert main(["mode", "static", "#12abCD"]) == 0
    assert load_config() == Config(mode="static", static_color="#12ABCD")
    assert read_requested_color() == (0x12, 0xAB, 0xCD)
    assert capsys.readouterr().out == "Mode static; queued #12ABCD\n"


def test_invalid_static_input_changes_nothing(xdg_dirs, capsys) -> None:
    save_config(Config(mode="dynamic", static_color="#112233"))
    request_color("#445566")
    assert main(["mode", "static", "bad"]) == 1
    assert load_config() == Config(mode="dynamic", static_color="#112233")
    assert read_requested_color() == (0x44, 0x55, 0x66)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: color must use #RRGGBB format\n"
    assert "Traceback" not in captured.err


def test_invalid_static_input_does_not_create_config_or_queue(xdg_dirs, capsys) -> None:
    assert main(["mode", "static", "bad"]) == 1
    assert not config_file().exists()
    assert read_requested_color() is None
    assert capsys.readouterr().err == "error: color must use #RRGGBB format\n"


def test_mode_dynamic_persists_external_color(xdg_dirs, capsys) -> None:
    save_config(Config(mode="static", static_color="#112233"))
    assert main(["mode", "dynamic", "#AABBCC"]) == 0
    assert load_config().mode == "dynamic"
    assert read_requested_color() == (0xAA, 0xBB, 0xCC)
    assert capsys.readouterr().out == "Mode dynamic; queued #AABBCC\n"


def test_api_version_json_contract(capsys) -> None:
    assert main(["api-version", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "apiVersion": 1,
        "daemonVersion": "0.1.0",
        "statusVersion": 1,
    }


def test_local_api_command_does_not_import_bleak() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from edifier_qr65.cli import main; "
            "assert 'bleak' not in sys.modules; raise SystemExit(main(['api-version']))",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr


def test_status_json_contract(xdg_dirs, capsys) -> None:
    save_config(Config(mode="static", static_color="#112233"))
    request_color("#112233", "static")
    write_runtime_status("connected", "#112233")
    assert main(["status", "--json"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert list(value) == [
        "version", "mode", "configuredStaticColor", "configuredBrightness",
        "colorMatching", "requestedColor", "requestedSource",
        "appliedColor", "appliedBrightness", "connection", "message", "updatedAt",
    ]
    assert value["requestedColor"] == value["appliedColor"] == "#112233"


def test_human_status_distinguishes_queued_and_applied(xdg_dirs, capsys) -> None:
    save_config(Config())
    request_color("#112233", "dynamic")
    write_runtime_status("connected", "#445566")
    assert main(["status"]) == 0
    output = capsys.readouterr().out
    assert "Requested (queued): #112233" in output
    assert "Applied (device confirmed): #445566" in output


def test_release_stops_service_and_persists_handoff_state(
    xdg_dirs, monkeypatch, capsys
) -> None:
    write_runtime_status("connected", "#112233", applied_brightness=40)
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or subprocess.CompletedProcess(command, 0, "", ""),
    )

    assert main(["release"]) == 0
    assert capsys.readouterr().out == "BLE released to ConneX\n"

    runtime = read_runtime_status()
    assert runtime["connection"] == "released"
    assert runtime["appliedColor"] == "#112233"
    assert runtime["appliedBrightness"] == 40
    assert calls[0][0] == ["/usr/bin/systemctl", "--user", "stop", "edifier-qr65.service"]


def test_resume_starts_service(xdg_dirs, monkeypatch, capsys) -> None:
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: calls.append(command)
        or subprocess.CompletedProcess(command, 0, "", ""),
    )

    assert main(["resume"]) == 0
    assert capsys.readouterr().out == "QR65 daemon resumed\n"
    assert calls == [["/usr/bin/systemctl", "--user", "start", "edifier-qr65.service"]]


def test_daemon_sigint_exits_cleanly(monkeypatch, capsys) -> None:
    def interrupted(_coroutine) -> None:
        _coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr("edifier_qr65.cli.asyncio.run", interrupted)

    assert main(["daemon"]) == 0
    assert capsys.readouterr().err == ""


def test_brightness_command_persists_value(xdg_dirs, capsys) -> None:
    assert main(["brightness", "64"]) == 0
    assert load_config().brightness == 64
    assert capsys.readouterr().out == "Brightness queued at 64%\n"


def test_invalid_brightness_changes_nothing(xdg_dirs, capsys) -> None:
    save_config(Config(brightness=40))
    assert main(["brightness", "101"]) == 1
    assert load_config().brightness == 40
    assert capsys.readouterr().err == "error: brightness must be between 0 and 100\n"


def test_color_matching_command_persists_state(xdg_dirs, capsys) -> None:
    assert main(["color-matching", "on"]) == 0
    assert load_config().color_matching is True
    assert capsys.readouterr().out == "Color matching enabled\n"

    assert main(["color-matching", "off"]) == 0
    assert load_config().color_matching is False
    assert capsys.readouterr().out == "Color matching disabled\n"

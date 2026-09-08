import json
import math
import subprocess

from edifier_qr65.cli import main
from edifier_qr65.config import Config, config_file, load_config, save_config
from edifier_qr65.status import read_runtime_status, write_runtime_status
from edifier_qr65.theme import read_requested_color, request_color


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


def test_mode_dynamic_persists_and_syncs(xdg_dirs, monkeypatch, capsys) -> None:
    save_config(Config(mode="static", static_color="#112233"))
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "#AABBCC\n", ""),
    )
    assert main(["mode", "dynamic"]) == 0
    assert load_config().mode == "dynamic"
    assert read_requested_color() == (0xAA, 0xBB, 0xCC)
    assert capsys.readouterr().out == "Mode dynamic; queued #AABBCC\n"


def test_theme_sync_static_is_noop(xdg_dirs, capsys) -> None:
    save_config(Config(mode="static", static_color="#112233"))
    request_color("#445566")
    assert main(["theme-sync"]) == 0
    assert read_requested_color() == (0x44, 0x55, 0x66)
    assert capsys.readouterr().out == "Static mode; theme sync ignored\n"


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
    request_color("#112233", "theme-accent")
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
    assert calls[0][0] == ["systemctl", "--user", "stop", "edifier-qr65.service"]


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
    assert calls == [["systemctl", "--user", "start", "edifier-qr65.service"]]


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

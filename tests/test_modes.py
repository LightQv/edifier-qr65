import subprocess
import threading
from pathlib import Path

import pytest

from edifier_qr65.config import Config, load_config, save_config
from edifier_qr65.theme import (
    read_requested_color,
    request_file,
    request_color,
    set_dynamic_mode,
    set_static_mode,
    sync_desired,
    sync_omarchy_accent,
)


def completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


def test_dynamic_accent_success_queues_validated_accent(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_config(Config(mode="dynamic", static_color="#112233"))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed("#89b4fa\n"))
    result = sync_desired()
    assert result.color == "#89B4FA"
    assert result.source == "theme-accent"
    assert read_requested_color() == (0x89, 0xB4, 0xFA)
    assert '"source":"theme-accent"' in request_file().read_text()


def test_omarchy_lookup_uses_three_second_inner_timeout(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_config(Config())

    def run(*args, **kwargs):
        assert kwargs["timeout"] == 3
        return completed("#112233")

    monkeypatch.setattr(subprocess, "run", run)
    sync_desired()


@pytest.mark.parametrize(
    "failure",
    [subprocess.CalledProcessError(1, ["omarchy"]),
     subprocess.TimeoutExpired(["omarchy"], 5), OSError("missing")],
)
def test_dynamic_lookup_failure_queues_fallback_and_preserves_mode(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    save_config(Config(mode="dynamic", static_color="#112233"))

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(subprocess, "run", fail)
    result = sync_desired()
    assert result.source == "static-fallback"
    assert read_requested_color() == (0x11, 0x22, 0x33)
    assert load_config().mode == "dynamic"


def test_invalid_dynamic_accent_uses_fallback(xdg_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    save_config(Config(mode="dynamic", static_color="#445566"))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed("not-a-color"))
    assert sync_desired().source == "static-fallback"
    assert read_requested_color() == (0x44, 0x55, 0x66)


def test_static_theme_hook_is_successful_noop(xdg_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    save_config(Config(mode="static", static_color="#ABCDEF"))
    request_color("#010203", "direct")

    def unexpected(*args, **kwargs):
        raise AssertionError("theme lookup must not run")

    monkeypatch.setattr(subprocess, "run", unexpected)
    assert sync_omarchy_accent() == "#ABCDEF"
    assert read_requested_color() == (1, 2, 3)


def test_explicit_sync_requeues_static_color(xdg_dirs) -> None:
    save_config(Config(mode="static", static_color="#ABCDEF"))
    request_color("#010203")
    result = sync_desired()
    assert result.source == "static"
    assert read_requested_color() == (0xAB, 0xCD, 0xEF)


def test_invalid_config_preserves_last_requested_color(xdg_dirs) -> None:
    request_color("#010203")
    save_config(Config())
    path = Path(xdg_dirs[0]) / "edifier-qr65" / "config.toml"
    path.write_text('version = 1\nmode = "dynamic"\nstatic_color = "bad"\n')
    with pytest.raises(ValueError):
        sync_desired()
    assert read_requested_color() == (1, 2, 3)


def test_concurrent_mode_changes_cannot_split_config_and_request(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_config(Config(mode="static", static_color="#010203"))
    resolving = threading.Event()
    release = threading.Event()
    static_started = threading.Event()
    static_done = threading.Event()

    def resolve() -> str:
        resolving.set()
        assert release.wait(2)
        return "#AABBCC"

    def dynamic() -> None:
        set_dynamic_mode()

    def static() -> None:
        static_started.set()
        set_static_mode("#445566")
        static_done.set()

    monkeypatch.setattr("edifier_qr65.theme._resolve_accent", resolve)
    dynamic_thread = threading.Thread(target=dynamic)
    static_thread = threading.Thread(target=static)
    dynamic_thread.start()
    assert resolving.wait(2)
    static_thread.start()
    assert static_started.wait(2)
    assert not static_done.wait(0.1)
    release.set()
    dynamic_thread.join(2)
    static_thread.join(2)

    assert not dynamic_thread.is_alive()
    assert not static_thread.is_alive()
    assert load_config() == Config(mode="static", static_color="#445566")
    assert read_requested_color() == (0x44, 0x55, 0x66)


def test_mode_changes_preserve_brightness_and_matching(xdg_dirs, monkeypatch) -> None:
    save_config(Config(mode="static", brightness=63, color_matching=False))
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: completed("#123456"))

    set_dynamic_mode()
    assert load_config() == Config(
        mode="dynamic", brightness=63, color_matching=False
    )

    set_static_mode("#ABCDEF")
    assert load_config() == Config(
        mode="static", static_color="#ABCDEF", brightness=63, color_matching=False
    )

import threading
from pathlib import Path

import pytest

from edifier_qr65.config import Config, load_config, save_config
from edifier_qr65.desired import (
    read_request,
    read_requested_color,
    request_color,
    set_dynamic_mode,
    set_static_mode,
    sync_desired,
)


def test_dynamic_mode_queues_explicit_external_color(xdg_dirs) -> None:
    save_config(Config(mode="static", static_color="#112233"))
    result = set_dynamic_mode("#89b4fa")

    assert result.color == "#89B4FA"
    assert result.source == "dynamic"
    assert load_config().mode == "dynamic"
    assert read_requested_color() == (0x89, 0xB4, 0xFA)
    assert read_request().source == "dynamic"


def test_dynamic_mode_does_not_rewrite_unchanged_config(xdg_dirs, monkeypatch) -> None:
    save_config(Config(mode="dynamic"))

    monkeypatch.setattr(
        "edifier_qr65.config.save_config",
        lambda *_args: (_ for _ in ()).throw(AssertionError("config is unchanged")),
    )

    assert set_dynamic_mode("#89B4FA").color == "#89B4FA"


def test_dynamic_mode_rejects_invalid_color_without_changes(xdg_dirs) -> None:
    save_config(Config(mode="static", static_color="#112233"))
    request_color("#445566", "static")

    with pytest.raises(ValueError, match="#RRGGBB"):
        set_dynamic_mode("invalid")

    assert load_config() == Config(mode="static", static_color="#112233")
    assert read_requested_color() == (0x44, 0x55, 0x66)


def test_explicit_sync_requeues_static_color(xdg_dirs) -> None:
    save_config(Config(mode="static", static_color="#ABCDEF"))
    request_color("#010203")
    result = sync_desired()

    assert result.source == "static"
    assert read_requested_color() == (0xAB, 0xCD, 0xEF)


def test_explicit_sync_requeues_dynamic_color(xdg_dirs) -> None:
    save_config(Config(mode="dynamic"))
    request_color("#ABCDEF", "dynamic")
    result = sync_desired()

    assert result.color == "#ABCDEF"
    assert result.source == "dynamic"
    assert read_requested_color() == (0xAB, 0xCD, 0xEF)


def test_dynamic_sync_requires_an_existing_request(xdg_dirs) -> None:
    save_config(Config(mode="dynamic"))
    with pytest.raises(ValueError, match="no requested color"):
        sync_desired()


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
    dynamic_started = threading.Event()
    release = threading.Event()
    static_started = threading.Event()
    static_done = threading.Event()

    original = __import__("edifier_qr65.desired", fromlist=["_request_color"])._request_color

    def blocked_request(value: str, source: str = "direct"):
        if source == "dynamic":
            dynamic_started.set()
            assert release.wait(2)
        return original(value, source)

    def dynamic() -> None:
        set_dynamic_mode("#AABBCC")

    def static() -> None:
        static_started.set()
        set_static_mode("#445566")
        static_done.set()

    monkeypatch.setattr("edifier_qr65.desired._request_color", blocked_request)
    dynamic_thread = threading.Thread(target=dynamic)
    static_thread = threading.Thread(target=static)
    dynamic_thread.start()
    assert dynamic_started.wait(2)
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


def test_mode_changes_preserve_brightness_and_matching(xdg_dirs) -> None:
    save_config(Config(mode="static", brightness=63, color_matching=False))

    set_dynamic_mode("#123456")
    assert load_config() == Config(
        mode="dynamic", brightness=63, color_matching=False
    )

    set_static_mode("#ABCDEF")
    assert load_config() == Config(
        mode="static", static_color="#ABCDEF", brightness=63, color_matching=False
    )

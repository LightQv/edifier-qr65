import pytest

from edifier_qr65.config import Config, config_file, load_config, save_config
from edifier_qr65.desired import request_color, state_file


def test_default_config_is_created_atomically(xdg_dirs) -> None:
    assert load_config() == Config()
    assert config_file().read_text() == (
        'version = 1\nmode = "dynamic"\nstatic_color = "#7DAEA3"\n'
        "color_matching = false\n"
    )
    assert not list(config_file().parent.glob(".config.toml-*"))


def test_legacy_color_becomes_initial_static_fallback(xdg_dirs) -> None:
    state_file().parent.mkdir(parents=True)
    state_file().write_text("#12abCD\n", encoding="ascii")
    assert load_config() == Config(static_color="#12ABCD")


def test_migration_prefers_authoritative_request_over_legacy_mirror(xdg_dirs) -> None:
    request_color("#112233", "static")
    state_file().write_text("#AABBCC\n", encoding="ascii")

    assert load_config() == Config(static_color="#112233")


@pytest.mark.parametrize("legacy", ["bad", "#123", "#GG0000"])
def test_invalid_legacy_color_uses_safe_default(xdg_dirs, legacy: str) -> None:
    state_file().parent.mkdir(parents=True)
    state_file().write_text(legacy, encoding="ascii")
    assert load_config().static_color == "#7DAEA3"


def test_existing_invalid_config_is_not_replaced(xdg_dirs) -> None:
    config_file().parent.mkdir(parents=True)
    original = 'version = 1\nmode = "broken"\nstatic_color = "#FFFFFF"\n'
    config_file().write_text(original)
    with pytest.raises(ValueError, match="mode"):
        load_config()
    assert config_file().read_text() == original


@pytest.mark.parametrize(
    "config, message",
    [(Config(version=2), "version"), (Config(mode="other"), "mode"),
     (Config(static_color="red"), "#RRGGBB")],
)
def test_save_rejects_invalid_config_without_replacing_existing(
    xdg_dirs, config: Config, message: str
) -> None:
    save_config(Config())
    original = config_file().read_bytes()
    with pytest.raises(ValueError, match=message):
        save_config(config)
    assert config_file().read_bytes() == original


def test_oversized_config_is_rejected(xdg_dirs) -> None:
    config_file().parent.mkdir(parents=True)
    config_file().write_bytes(b" " * (64 * 1024 + 1))
    with pytest.raises(ValueError, match="too large"):
        load_config()


def test_non_string_static_color_is_rejected_concisely(xdg_dirs) -> None:
    config_file().parent.mkdir(parents=True)
    config_file().write_text('version = 1\nmode = "dynamic"\nstatic_color = 123\n')
    with pytest.raises(ValueError, match="#RRGGBB"):
        load_config()


def test_old_config_defaults_to_raw_rgb_and_preserved_device_brightness(xdg_dirs) -> None:
    config_file().parent.mkdir(parents=True)
    config_file().write_text('version = 1\nmode = "dynamic"\nstatic_color = "#123456"\n')

    assert load_config() == Config(static_color="#123456")


def test_brightness_and_matching_are_persisted(xdg_dirs) -> None:
    save_config(Config(brightness=37, color_matching=False))

    assert load_config() == Config(brightness=37, color_matching=False)
    assert "brightness = 37\n" in config_file().read_text()
    assert "color_matching = false\n" in config_file().read_text()


@pytest.mark.parametrize(
    "config, message",
    [
        (Config(brightness=-1), "brightness"),
        (Config(brightness=101), "brightness"),
        (Config(brightness=True), "brightness"),
        (Config(color_matching=1), "color_matching"),
    ],
)
def test_new_config_fields_are_validated(xdg_dirs, config: Config, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        save_config(config)

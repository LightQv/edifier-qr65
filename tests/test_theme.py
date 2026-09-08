import json
import multiprocessing

import pytest

from edifier_qr65.theme import (
    operation_lock,
    ownership_lock,
    parse_rgb,
    read_request,
    read_requested_color,
    request_color,
    request_file,
    state_file,
)


def _wait_for_operation_lock(ready, acquired) -> None:
    ready.set()
    with operation_lock():
        acquired.set()


def test_parse_rgb() -> None:
    assert parse_rgb("#12aBcD") == (0x12, 0xAB, 0xCD)


@pytest.mark.parametrize("value", ["12ABCD", "#123", "#12345678", "#GG0000", ""])
def test_parse_rgb_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="#RRGGBB"):
        parse_rgb(value)


def test_request_color_replaces_state_without_temporary_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    request_color("#12abcd")

    assert read_requested_color() == (0x12, 0xAB, 0xCD)
    assert state_file().read_text(encoding="ascii") == "#12ABCD\n"
    assert list(state_file().parent.glob(".color-*")) == []


def test_request_json_is_authoritative_over_compatibility_mirror(xdg_dirs) -> None:
    request_color("#112233", "static")
    state_file().write_text("#AABBCC\n", encoding="ascii")

    assert read_requested_color() == (0x11, 0x22, 0x33)
    assert read_request().source == "static"


def test_malformed_authoritative_request_never_falls_back_to_mirror(xdg_dirs) -> None:
    request_color("#112233")
    request_file().write_text("not json", encoding="utf-8")
    state_file().write_text("#AABBCC\n", encoding="ascii")

    with pytest.raises(ValueError, match="malformed"):
        read_requested_color()


def test_missing_request_json_reads_safe_legacy_color(xdg_dirs) -> None:
    state_file().parent.mkdir(parents=True)
    state_file().write_text("#aabbcc\n", encoding="ascii")

    request = read_request()

    assert request is not None
    assert request.color == "#AABBCC"
    assert request.source == ""


def test_request_json_contains_complete_atomic_contract(xdg_dirs) -> None:
    request_color("#ABCDEF", "theme-accent")

    data = json.loads(request_file().read_text())

    assert data["version"] == 1
    assert data["color"] == "#ABCDEF"
    assert data["source"] == "theme-accent"
    assert type(data["updatedAt"]) is int
    assert not list(request_file().parent.glob(".request-*"))


def test_repeated_request_gets_new_generation(xdg_dirs, monkeypatch) -> None:
    monkeypatch.setattr("edifier_qr65.theme.time.time", lambda: 100)
    request_color("#112233")
    first = read_request()
    request_color("#112233")
    second = read_request()

    assert first is not None and second is not None
    assert second.updated_at == first.updated_at + 1


def test_operation_lock_blocks_another_process(xdg_dirs) -> None:
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    acquired = context.Event()

    with operation_lock():
        process = context.Process(target=_wait_for_operation_lock, args=(ready, acquired))
        process.start()
        assert ready.wait(2)
        assert not acquired.wait(0.1)

    assert acquired.wait(2)
    process.join(2)
    assert process.exitcode == 0


def test_nonblocking_ble_ownership_refuses_second_owner(xdg_dirs) -> None:
    with ownership_lock():
        with pytest.raises(RuntimeError, match="already owned"):
            with ownership_lock(blocking=False):
                pass

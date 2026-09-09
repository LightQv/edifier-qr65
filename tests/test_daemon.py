import asyncio
from types import SimpleNamespace

import pytest

from edifier_qr65 import daemon
from edifier_qr65.ble import ColorApplicationError
from edifier_qr65.color import match_rgb
from edifier_qr65.protocol import AmbientLightState, LightMode
from edifier_qr65.desired import request_color, state_file


class ImmediateEvent:
    async def wait(self) -> bool:
        return False


def test_daemon_keeps_last_good_color_when_queue_becomes_malformed(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    from edifier_qr65.config import Config, save_config

    request_color("#010203")
    save_config(Config(color_matching=True))
    writes: list[tuple[int, int, int, int]] = []

    class Client:
        reads = 0

        @property
        def is_connected(self) -> bool:
            self.reads += 1
            return self.reads <= 3

    class Connection:
        client = Client()
        disconnected = ImmediateEvent()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def initialize(self):
            static = LightMode(7, 0, 0, 0, 50, 255)
            return None, None, AmbientLightState(4, 7, (static,))

        async def apply_static_color(
            self, red: int, green: int, blue: int, *, brightness: int | None
        ):
            effective_brightness = 50 if brightness is None else brightness
            writes.append((red, green, blue, effective_brightness))
            state_file().write_text("malformed", encoding="ascii")
            return effective_brightness, b"packet"

    calls = 0

    async def discover(_timeout: float):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise asyncio.CancelledError
        return [SimpleNamespace(device=object())]

    monkeypatch.setattr(daemon, "discover", discover)
    monkeypatch.setattr(daemon, "QR65Connection", lambda *_args: Connection())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(daemon.run())
    matched = match_rgb(1, 2, 3)
    assert writes == [(*matched, 50)]
    assert f'"appliedColor":"#{matched[0]:02X}{matched[1]:02X}{matched[2]:02X}"' in (
        state_file().with_name("status.json").read_text(encoding="utf-8")
    )
    assert '"appliedBrightness":50' in (
        state_file().with_name("status.json").read_text(encoding="utf-8")
    )


def test_daemon_reports_scanning_and_activation_required(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    phases: list[str] = []
    calls = 0

    async def discover(_timeout: float):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise asyncio.CancelledError
        return []

    async def sleep(_delay: float):
        return None

    monkeypatch.setattr(daemon, "discover", discover)
    monkeypatch.setattr(daemon.asyncio, "sleep", sleep)
    monkeypatch.setattr(
        daemon, "write_runtime_status", lambda connection, *_args, **_kwargs: phases.append(connection)
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(daemon.run())
    assert phases == ["starting", "scanning", "activation-required", "scanning"]


def test_daemon_applies_brightness_and_literal_mode(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    from edifier_qr65.config import Config, save_config

    request_color("#E68E0D")
    save_config(Config(brightness=61, color_matching=False))
    writes: list[tuple[int, int, int, int]] = []

    class Client:
        reads = 0

        @property
        def is_connected(self) -> bool:
            self.reads += 1
            return self.reads <= 2

    class Connection:
        client = Client()
        disconnected = ImmediateEvent()

        async def __aenter__(self): return self
        async def __aexit__(self, *_exc): return None
        async def initialize(self):
            return None, None, AmbientLightState(4, 7, (LightMode(7, 0, 0, 0, 50, 255),))
        async def apply_static_color(self, red, green, blue, *, brightness):
            writes.append((red, green, blue, brightness))
            return brightness, b"packet"

    calls = 0

    async def discover(_timeout):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise asyncio.CancelledError
        return [SimpleNamespace(device=object())]

    monkeypatch.setattr(daemon, "discover", discover)
    monkeypatch.setattr(daemon, "QR65Connection", lambda *_args: Connection())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(daemon.run())
    assert writes == [(0xE6, 0x8E, 0x0D, 61)]


def test_daemon_blocks_repeated_write_after_failed_confirmation(
    xdg_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_color("#010203")
    writes = 0

    class Client:
        reads = 0

        @property
        def is_connected(self) -> bool:
            self.reads += 1
            return self.reads <= 3

    class Connection:
        client = Client()
        disconnected = ImmediateEvent()

        async def __aenter__(self): return self
        async def __aexit__(self, *_exc): return None
        async def initialize(self):
            return None, None, AmbientLightState(4, 7, (LightMode(7, 0, 0, 0, 50, 255),))
        async def apply_static_color(self, *_rgb, brightness=None):
            nonlocal writes
            writes += 1
            raise ColorApplicationError("QR65 did not confirm the requested static color")

    calls = 0

    async def discover(_timeout):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise asyncio.CancelledError
        return [SimpleNamespace(device=object())]

    monkeypatch.setattr(daemon, "discover", discover)
    monkeypatch.setattr(daemon, "QR65Connection", lambda *_args: Connection())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(daemon.run())
    assert writes == 1

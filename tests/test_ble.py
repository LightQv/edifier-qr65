import asyncio
from types import SimpleNamespace

import pytest

from edifier_qr65.ble import (
    QR65_SEARCH_UUIDS,
    QR65_SERVICE_UUIDS,
    ColorApplicationError,
    DiscoveredDevice,
    QR65Connection,
    WRITE_UUID,
    set_static_color,
)
from edifier_qr65.protocol import AMBIENT_LIGHT_QUERY, APP_CODE, Frame, decode_ambient_light


def ambient_frame(
    red: int,
    green: int,
    blue: int,
    *,
    selected: int = 7,
    array: int = 4,
    brightness: int = 42,
) -> Frame:
    return Frame(
        0xBB,
        APP_CODE,
        AMBIENT_LIGHT_QUERY,
        bytes((array, selected, 7, red, green, blue, brightness, 255)),
    )


def test_only_tested_global_variant_is_supported() -> None:
    assert QR65_SEARCH_UUIDS == {"00005d00-0000-1000-8000-00805f9b34fb"}
    assert QR65_SERVICE_UUIDS == {"48095d01-1a48-11e9-ab14-d663bd873d93"}


def test_discovery_requires_edifier_manufacturer_data() -> None:
    advertisement = SimpleNamespace(
        service_uuids=["00005d00-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={},
    )
    assert DiscoveredDevice(SimpleNamespace(), advertisement).is_qr65 is False
    advertisement.manufacturer_data[0x07E0] = b"\x00"
    assert DiscoveredDevice(SimpleNamespace(), advertisement).is_qr65 is True


def test_connection_rejects_device_without_tested_service() -> None:
    connection = QR65Connection.__new__(QR65Connection)

    class Client:
        is_connected = True
        services = [SimpleNamespace(uuid="48093901-1a48-11e9-ab14-d663bd873d93")]

        async def connect(self) -> None: return None
        async def disconnect(self) -> None: self.is_connected = False
        async def start_notify(self, *_args) -> None: raise AssertionError("must not notify")

    connection.client = Client()

    with pytest.raises(RuntimeError, match="tested global QR65 service"):
        asyncio.run(connection.__aenter__())
    assert connection.client.is_connected is False


def test_query_discards_stale_responses() -> None:
    connection = QR65Connection.__new__(QR65Connection)
    connection.query_lock = asyncio.Lock()
    connection.responses = asyncio.Queue()
    connection.disconnected = asyncio.Event()
    connection.responses.put_nowait(ambient_frame(1, 2, 3))

    async def write(_uuid: str, _packet: bytes, response: bool) -> None:
        assert response is True
        connection.responses.put_nowait(ambient_frame(4, 5, 6))

    connection.client = SimpleNamespace(write_gatt_char=write)
    connection.timeout = 1

    response = asyncio.run(connection.query(AMBIENT_LIGHT_QUERY))
    assert response.payload[3:6] == bytes((4, 5, 6))


def test_apply_static_color_preserves_brightness_and_verifies(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = QR65Connection.__new__(QR65Connection)
    responses = iter((ambient_frame(1, 2, 3), ambient_frame(10, 20, 30)))
    writes: list[tuple[str, bytes, bool]] = []

    async def query(_command: int) -> Frame:
        return next(responses)

    async def write(uuid: str, packet: bytes, response: bool) -> None:
        writes.append((uuid, packet, response))

    async def sleep(_delay: float) -> None:
        return None

    connection.query = query
    connection.client = SimpleNamespace(write_gatt_char=write)
    monkeypatch.setattr("edifier_qr65.ble.asyncio.sleep", sleep)

    brightness, _packet = asyncio.run(connection.apply_static_color(10, 20, 30))

    assert brightness == 42
    assert writes[0][0] == WRITE_UUID
    assert writes[0][2] is False


def test_apply_static_color_rejects_unconfirmed_readback(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = QR65Connection.__new__(QR65Connection)
    responses = iter((ambient_frame(1, 2, 3), ambient_frame(1, 2, 3)))

    async def query(_command: int) -> Frame:
        return next(responses)

    async def write(_uuid: str, _packet: bytes, response: bool) -> None:
        del response
        return None

    async def sleep(_delay: float) -> None:
        return None

    connection.query = query
    connection.client = SimpleNamespace(write_gatt_char=write)
    monkeypatch.setattr("edifier_qr65.ble.asyncio.sleep", sleep)

    with pytest.raises(RuntimeError, match="did not confirm"):
        asyncio.run(connection.apply_static_color(10, 20, 30))


@pytest.mark.parametrize("failure", [TimeoutError(), ConnectionError("disconnected")])
def test_apply_static_color_wraps_confirmation_transport_failures(failure) -> None:
    connection = QR65Connection.__new__(QR65Connection)

    async def write(*_args):
        raise failure

    connection.set_color = write
    state = ambient_frame(1, 2, 3)

    with pytest.raises(ColorApplicationError, match="did not confirm"):
        asyncio.run(
            connection.apply_static_color(
                10, 20, 30, state=decode_ambient_light(state)
            )
        )


@pytest.mark.parametrize(
    "confirmed",
    [ambient_frame(10, 20, 30, array=3), ambient_frame(10, 20, 30, brightness=41)],
)
def test_apply_static_color_rejects_wrong_array_or_brightness(
    confirmed: Frame, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = QR65Connection.__new__(QR65Connection)
    confirmations = (confirmed,) * (3 if confirmed.payload[0] != 4 else 1)
    responses = iter((ambient_frame(1, 2, 3), *confirmations))

    async def query(_command: int) -> Frame:
        return next(responses)

    async def write(_uuid: str, _packet: bytes, response: bool) -> None:
        del response

    async def sleep(_delay: float) -> None:
        return None

    connection.query = query
    connection.client = SimpleNamespace(write_gatt_char=write)
    monkeypatch.setattr("edifier_qr65.ble.asyncio.sleep", sleep)

    with pytest.raises(RuntimeError, match="did not confirm"):
        asyncio.run(connection.apply_static_color(10, 20, 30))


def test_ambient_query_retries_transient_other_array() -> None:
    connection = QR65Connection.__new__(QR65Connection)
    responses = iter((
        ambient_frame(1, 2, 3, array=1),
        ambient_frame(1, 2, 3, array=4),
    ))

    async def query(_command: int) -> Frame:
        return next(responses)

    connection.query = query

    _frame, state = asyncio.run(connection._query_qr65_ambient())
    assert state.array_index == 4


def test_apply_retries_transient_other_array_during_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = QR65Connection.__new__(QR65Connection)
    responses = iter((
        ambient_frame(1, 2, 3),
        ambient_frame(10, 20, 30, array=1),
        ambient_frame(10, 20, 30),
    ))

    async def query(_command: int) -> Frame:
        return next(responses)

    async def write(_uuid: str, _packet: bytes, response: bool) -> None:
        del response

    async def sleep(_delay: float) -> None:
        return None

    connection.query = query
    connection.client = SimpleNamespace(write_gatt_char=write)
    monkeypatch.setattr("edifier_qr65.ble.asyncio.sleep", sleep)

    brightness, _packet = asyncio.run(connection.apply_static_color(10, 20, 30))
    assert brightness == 42


def test_apply_static_color_sets_explicit_brightness(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = QR65Connection.__new__(QR65Connection)
    responses = iter((ambient_frame(1, 2, 3, brightness=42), ambient_frame(10, 20, 30, brightness=65)))
    writes: list[bytes] = []

    async def query(_command: int) -> Frame:
        return next(responses)

    async def write(_uuid: str, packet: bytes, response: bool) -> None:
        del response
        writes.append(packet)

    async def sleep(_delay: float) -> None:
        return None

    connection.query = query
    connection.client = SimpleNamespace(write_gatt_char=write)
    monkeypatch.setattr("edifier_qr65.ble.asyncio.sleep", sleep)

    brightness, _packet = asyncio.run(
        connection.apply_static_color(10, 20, 30, brightness=65)
    )

    assert brightness == 65
    assert writes[0][-3] == 65


def test_one_shot_static_write_passes_initialized_state_by_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ambient = object()
    seen = {}

    class Connection:
        async def __aenter__(self): return self
        async def __aexit__(self, *_exc): return None
        async def initialize(self): return None, None, ambient
        async def apply_static_color(self, red, green, blue, **kwargs):
            seen.update(rgb=(red, green, blue), kwargs=kwargs)
            return 50, b"packet"

    monkeypatch.setattr(
        "edifier_qr65.ble.QR65Connection", lambda *_args: Connection()
    )

    assert asyncio.run(set_static_color("device", 1, 2, 3, 10)) == (50, b"packet")
    assert seen == {"rgb": (1, 2, 3), "kwargs": {"state": ambient}}

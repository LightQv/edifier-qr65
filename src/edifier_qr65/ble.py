"""BLE discovery and inspection for Edifier QR65 speakers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .protocol import (
    APP_CODE,
    AMBIENT_LIGHT_QUERY,
    AmbientLightState,
    QR65_STATIC_MODE,
    QR65_LIGHT_ARRAY,
    QR65_SERVICE_UUIDS,
    SUPPORT_QUERY,
    Frame,
    decode_ambient_light,
    decode_v2,
    encode_static_color,
    encode_v2,
)

LOG = logging.getLogger(__name__)
MAX_FRAME_SIZE = 1024

EDIFIER_MANUFACTURER_ID = 0x07E0
QR65_SEARCH_UUIDS = {
    "00005d00-0000-1000-8000-00805f9b34fb",
}
READ_UUID = "48090001-1a48-11e9-ab14-d663bd873d93"
WRITE_UUID = "48090002-1a48-11e9-ab14-d663bd873d93"


class ColorApplicationError(RuntimeError):
    """A color write or its confirmation failed and must not be repeated."""


@dataclass(frozen=True)
class DiscoveredDevice:
    """A BLE device and its latest advertisement."""

    device: BLEDevice
    advertisement: AdvertisementData

    @property
    def is_qr65(self) -> bool:
        """Return whether advertisement data identifies the tested QR65."""
        advertised = {uuid.lower() for uuid in self.advertisement.service_uuids}
        return (
            bool(advertised & QR65_SEARCH_UUIDS)
            and EDIFIER_MANUFACTURER_ID in self.advertisement.manufacturer_data
        )


async def discover(
    timeout: float, include_all: bool = False
) -> list[DiscoveredDevice]:
    """Discover QR65 candidates, optionally including unrelated BLE devices."""
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    devices = [
        DiscoveredDevice(device, advertisement)
        for device, advertisement in found.values()
    ]
    if not include_all:
        devices = [item for item in devices if item.is_qr65]
    return sorted(devices, key=lambda item: item.advertisement.rssi, reverse=True)


async def inspect(device: BLEDevice | str, timeout: float) -> list[tuple[str, list[str]]]:
    """Connect without writing and return the device's GATT characteristics."""
    async with BleakClient(device, timeout=timeout) as client:
        return [
            (service.uuid, [f"{char.uuid} ({','.join(char.properties)})" for char in service.characteristics])
            for service in client.services
        ]


class QR65Connection:
    """One initialized QR65 GATT control connection."""

    def __init__(self, device: BLEDevice | str, timeout: float) -> None:
        self.timeout = timeout
        self.responses: asyncio.Queue[Frame] = asyncio.Queue(maxsize=16)
        self.pending = bytearray()
        self.disconnected = asyncio.Event()
        self.query_lock = asyncio.Lock()
        self.client = BleakClient(
            device,
            timeout=timeout,
            disconnected_callback=lambda _client: self.disconnected.set(),
        )

    def _receive(self, _characteristic: object, data: bytearray) -> None:
        self.pending.extend(data)
        while len(self.pending) >= 6:
            if self.pending[0] not in (0xBB, 0xCC):
                self.pending.pop(0)
                continue
            frame_length = int.from_bytes(self.pending[3:5], "big") + 6
            if frame_length > MAX_FRAME_SIZE:
                LOG.warning("discarding implausible %d-byte protocol frame", frame_length)
                self.pending.pop(0)
                continue
            if len(self.pending) < frame_length:
                return
            packet = bytes(self.pending[:frame_length])
            del self.pending[:frame_length]
            try:
                frame = decode_v2(packet)
            except ValueError as error:
                LOG.warning("discarding malformed protocol frame: %s", error)
                continue
            if self.responses.full():
                self.responses.get_nowait()
            self.responses.put_nowait(frame)

    async def __aenter__(self) -> QR65Connection:
        try:
            await self.client.connect()
            services = {service.uuid.lower() for service in self.client.services}
            if not services & QR65_SERVICE_UUIDS:
                raise RuntimeError("device does not expose the tested global QR65 service")
            await self.client.start_notify(READ_UUID, self._receive)
            return self
        except BaseException:
            if self.client.is_connected:
                await self.client.disconnect()
            raise

    async def __aexit__(self, *_exc: object) -> None:
        try:
            if self.client.is_connected:
                await self.client.stop_notify(READ_UUID)
        except BleakError as error:
            LOG.warning("failed to stop notifications: %s", error)
        finally:
            if self.client.is_connected:
                await self.client.disconnect()

    async def _next_response(self) -> Frame:
        response = asyncio.create_task(self.responses.get())
        disconnected = asyncio.create_task(self.disconnected.wait())
        tasks = (response, disconnected)
        try:
            done, _pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            if disconnected in done:
                raise ConnectionError("QR65 disconnected while awaiting a response")
            return response.result()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def query(self, command: int) -> Frame:
        """Send an allowlisted query and await its matching response."""
        if command not in (SUPPORT_QUERY, AMBIENT_LIGHT_QUERY):
            raise ValueError(f"query command 0x{command:02X} is not allowed")
        async with self.query_lock:
            while not self.responses.empty():
                self.responses.get_nowait()
            await self.client.write_gatt_char(WRITE_UUID, encode_v2(command), response=True)
            async with asyncio.timeout(self.timeout):
                while True:
                    frame = await self._next_response()
                    if frame.app_code == APP_CODE and frame.command == command:
                        return frame

    async def initialize(self) -> tuple[Frame, Frame, AmbientLightState]:
        """Run the ConneX initialization sequence and read lighting state."""
        support = await self.query(SUPPORT_QUERY)
        ambient_frame, state = await self._query_qr65_ambient()
        return support, ambient_frame, state

    async def _query_qr65_ambient(self) -> tuple[Frame, AmbientLightState]:
        """Read array 4, tolerating transient reports for another light array."""
        last_array: int | None = None
        for _attempt in range(3):
            frame = await self.query(AMBIENT_LIGHT_QUERY)
            state = decode_ambient_light(frame)
            if state.array_index == QR65_LIGHT_ARRAY:
                return frame, state
            last_array = state.array_index
        raise RuntimeError(
            f"expected QR65 lighting array {QR65_LIGHT_ARRAY}, got {last_array}"
        )

    async def set_color(
        self, red: int, green: int, blue: int, brightness: int
    ) -> bytes:
        """Write only the captured array-4 static-color command."""
        packet = encode_static_color(red, green, blue, brightness)
        await self.client.write_gatt_char(WRITE_UUID, packet, response=False)
        return packet

    async def apply_static_color(
        self,
        red: int,
        green: int,
        blue: int,
        brightness: int | None = None,
        state: AmbientLightState | None = None,
    ) -> tuple[int, bytes]:
        """Apply static RGB using current brightness and verify device readback."""
        if state is None:
            _frame, state = await self._query_qr65_ambient()
        if state.array_index != QR65_LIGHT_ARRAY:
            raise RuntimeError(
                f"expected QR65 lighting array {QR65_LIGHT_ARRAY}, got {state.array_index}"
            )
        static = next(
            (mode for mode in state.modes if mode.index == QR65_STATIC_MODE), None
        )
        if static is None:
            raise RuntimeError("QR65 did not report static lighting mode 7")

        desired_brightness = static.brightness if brightness is None else brightness
        try:
            packet = await self.set_color(red, green, blue, desired_brightness)
            await asyncio.sleep(0.2)
            _frame, confirmed = await self._query_qr65_ambient()
        except (BleakError, ConnectionError, TimeoutError, RuntimeError) as error:
            raise ColorApplicationError(
                "QR65 did not confirm the requested static color"
            ) from error
        confirmed_static = next(
            (mode for mode in confirmed.modes if mode.index == QR65_STATIC_MODE), None
        )
        if (
            confirmed.array_index != QR65_LIGHT_ARRAY
            or confirmed.selected_mode != QR65_STATIC_MODE
            or confirmed_static is None
            or (confirmed_static.red, confirmed_static.green, confirmed_static.blue)
            != (red, green, blue)
            or confirmed_static.brightness != desired_brightness
        ):
            raise ColorApplicationError("QR65 did not confirm the requested static color")
        return desired_brightness, packet


async def query_ambient_light(device: BLEDevice | str, timeout: float) -> tuple[Frame, Frame]:
    """Run the app's read-only initialization and ambient-light queries."""
    async with QR65Connection(device, timeout) as connection:
        support, ambient, _state = await connection.initialize()
        return support, ambient


async def set_static_color(
    device: BLEDevice | str,
    red: int,
    green: int,
    blue: int,
    timeout: float,
    delay: float = 0,
) -> tuple[int, bytes]:
    """Set static RGB after querying and preserving the current brightness."""
    async with QR65Connection(device, timeout) as connection:
        _support, _ambient_frame, ambient = await connection.initialize()
        if delay:
            await asyncio.sleep(delay)
            ambient = None
        return await connection.apply_static_color(red, green, blue, state=ambient)

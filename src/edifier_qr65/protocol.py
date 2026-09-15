"""Confirmed Edifier ConneX BLE protocol primitives."""

from __future__ import annotations

from dataclasses import dataclass

APP_CODE = 0xEC
SEND_HEADER = 0xAA
RECEIVE_HEADERS = {0xBB, 0xCC}
SUPPORT_QUERY = 0xD8
AMBIENT_LIGHT_QUERY = 0x6A
AMBIENT_LIGHT_SET = 0x6B
QR65_LIGHT_ARRAY = 4
QR65_STATIC_MODE = 7
QR65_SERVICE_UUIDS = {
    "48095d01-1a48-11e9-ab14-d663bd873d93",
}


@dataclass(frozen=True)
class Frame:
    """A validated protocol V2 frame."""

    header: int
    app_code: int
    command: int
    payload: bytes


@dataclass(frozen=True)
class LightMode:
    """One six-byte ambient-light mode record."""

    index: int
    red: int
    green: int
    blue: int
    brightness: int
    wire_speed: int


@dataclass(frozen=True)
class AmbientLightState:
    """Decoded response to command 0x6A."""

    array_index: int
    selected_mode: int
    modes: tuple[LightMode, ...]


def encode_v2(command: int, payload: bytes = b"") -> bytes:
    """Encode an unencrypted ConneX protocol V2 command."""
    if not 0 <= command <= 0xFF:
        raise ValueError("command must fit in one byte")
    if len(payload) > 0xFFFF:
        raise ValueError("payload is too large")
    prefix = bytes((SEND_HEADER, APP_CODE, command, len(payload) >> 8, len(payload) & 0xFF)) + payload
    return prefix + bytes((sum(prefix) & 0xFF,))


def decode_v2(packet: bytes) -> Frame:
    """Validate and decode one complete ConneX protocol V2 frame."""
    if len(packet) < 6:
        raise ValueError("frame is shorter than six bytes")
    if packet[0] not in RECEIVE_HEADERS:
        raise ValueError(f"unexpected receive header 0x{packet[0]:02X}")
    payload_length = int.from_bytes(packet[3:5], "big")
    if len(packet) != payload_length + 6:
        raise ValueError("frame length does not match payload length")
    if packet[-1] != sum(packet[:-1]) & 0xFF:
        raise ValueError("frame checksum is invalid")
    return Frame(packet[0], packet[1], packet[2], packet[5:-1])


def decode_ambient_light(frame: Frame) -> AmbientLightState:
    """Decode the QR65 ambient-light query response."""
    if frame.app_code != APP_CODE or frame.command != AMBIENT_LIGHT_QUERY:
        raise ValueError("frame is not an ambient-light query response")
    if len(frame.payload) < 2 or (len(frame.payload) - 2) % 6:
        raise ValueError("ambient-light payload has an unexpected length")

    modes = tuple(
        LightMode(*frame.payload[offset : offset + 6])
        for offset in range(2, len(frame.payload), 6)
    )
    return AmbientLightState(frame.payload[0], frame.payload[1], modes)


def encode_static_color(red: int, green: int, blue: int, brightness: int = 50) -> bytes:
    """Encode the captured QR65 array-4 static-color command."""
    values = (red, green, blue)
    if any(value < 0 or value > 0xFF for value in values):
        raise ValueError("RGB channels must be between 0 and 255")
    if not 0 <= brightness <= 100:
        raise ValueError("brightness must be between 0 and 100")
    payload = bytes(
        (QR65_LIGHT_ARRAY, QR65_STATIC_MODE, red, green, blue, brightness, 0xFF)
    )
    return encode_v2(AMBIENT_LIGHT_SET, payload)

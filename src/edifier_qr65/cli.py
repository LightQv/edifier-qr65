"""Command-line interface for QR65 discovery and inspection."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import math
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from bleak.exc import BleakError

from . import __version__, daemon
from .ble import EDIFIER_MANUFACTURER_ID, discover, inspect, query_ambient_light, set_static_color
from .config import load_config
from .protocol import decode_ambient_light, encode_static_color
from .status import build_status, read_runtime_status, status_file, write_runtime_status
from .desired import (
    parse_rgb,
    request_color,
    ownership_lock,
    set_dynamic_mode,
    set_brightness,
    set_color_matching,
    set_static_mode,
    sync_desired,
)

SERVICE_UNIT = "edifier-qr65.service"


@contextmanager
def _control_lock() -> Iterator[None]:
    """Serialize daemon lifecycle operations without blocking color updates."""
    path = status_file().with_name("control.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edifier-qr65")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="discover QR65 BLE advertisements without connecting")
    scan.add_argument("--timeout", type=float, default=10.0)
    scan.add_argument("--all", action="store_true", help="show unrelated BLE devices too")

    inspect_command = commands.add_parser("inspect", help="connect and list GATT services without writing")
    inspect_command.add_argument("--device", help="BLE address; discovers the QR65 when omitted")
    inspect_command.add_argument("--timeout", type=float, default=10.0)

    query = commands.add_parser("query-light", help="query current lighting state without changing it")
    query.add_argument("--device", help="BLE address; discovers the QR65 when omitted")
    query.add_argument("--timeout", type=float, default=10.0)

    color = commands.add_parser("set-color", help="set the captured QR65 static-color mode")
    color.add_argument("color", help="RGB color in #RRGGBB format")
    color.add_argument("--device", help="BLE address; discovers the QR65 when omitted")
    color.add_argument("--timeout", type=float, default=10.0)
    color.add_argument("--direct", action="store_true", help="connect and write without the daemon")
    color.add_argument("--delay", type=float, default=0, help=argparse.SUPPRESS)
    color.add_argument("--dry-run", action="store_true", help="print a 50%% brightness packet without BLE")

    api_version = commands.add_parser("api-version", help="show the stable consumer API version")
    api_version.add_argument("--json", action="store_true", dest="as_json")
    mode = commands.add_parser("mode", help="select externally driven dynamic or static lighting")
    mode.add_argument("mode", choices=("dynamic", "static"))
    mode.add_argument("color", help="color in #RRGGBB format")
    commands.add_parser("sync", help="reapply the desired configured color")
    brightness = commands.add_parser("brightness", help="set persistent LED brightness")
    brightness.add_argument("percent", type=int)
    matching = commands.add_parser("color-matching", help="enable or disable built-in matching")
    matching.add_argument("state", choices=("on", "off"))
    commands.add_parser("release", help="release BLE control to the official ConneX app")
    commands.add_parser("resume", help="resume the persistent BLE daemon")
    status = commands.add_parser("status", help="show configured and daemon-reported state")
    status.add_argument("--json", action="store_true", dest="as_json")
    commands.add_parser("daemon", help="hold BLE and apply queued colors")
    return parser


def _positive_float(value: float, name: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return value


def _nonnegative_float(value: float, name: str) -> float:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return value


def _daemon_is_active() -> bool:
    result = subprocess.run(
        ["/usr/bin/systemctl", "--user", "is-active", "--quiet", SERVICE_UNIT],
        check=False,
        capture_output=True,
        timeout=5,
    )
    return result.returncode == 0


async def _scan(timeout: float, include_all: bool) -> int:
    timeout = _positive_float(timeout, "timeout")
    devices = await discover(timeout, include_all)
    if not devices:
        print("No QR65 BLE advertisement found.")
        return 1

    for item in devices:
        advertisement = item.advertisement
        name = advertisement.local_name or item.device.name or "(unnamed)"
        marker = "QR65" if item.is_qr65 else "other"
        print(f"{marker:5} {item.device.address}  RSSI {advertisement.rssi:4}  {name}")
        if advertisement.service_uuids:
            print(f"      services: {', '.join(advertisement.service_uuids)}")
        for company_id, payload in advertisement.manufacturer_data.items():
            company = "Edifier" if company_id == EDIFIER_MANUFACTURER_ID else "unknown"
            print(f"      manufacturer: 0x{company_id:04X} ({company}) {payload.hex(' ')}")
    return 0


async def _inspect(address: str | None, timeout: float) -> int:
    timeout = _positive_float(timeout, "timeout")
    with ownership_lock(blocking=False):
        device = address
        if address is None:
            devices = await discover(timeout)
            if len(devices) != 1:
                print(f"Expected one QR65 advertisement, found {len(devices)}.")
                return 1
            device = devices[0].device

        assert device is not None
        for service_uuid, characteristics in await inspect(device, timeout):
            print(service_uuid)
            for characteristic in characteristics:
                print(f"  {characteristic}")
    return 0


async def _query_light(address: str | None, timeout: float) -> int:
    timeout = _positive_float(timeout, "timeout")
    with ownership_lock(blocking=False):
        device = address
        if address is None:
            devices = await discover(timeout)
            if len(devices) != 1:
                print(f"Expected one QR65 advertisement, found {len(devices)}.")
                return 1
            device = devices[0].device

        assert device is not None
        support, ambient = await query_ambient_light(device, timeout)
    state = decode_ambient_light(ambient)
    print(f"support 0xD8: {support.payload.hex(' ')}")
    print(f"array: {state.array_index}; selected mode: {state.selected_mode}")
    for mode in state.modes:
        print(
            f"mode {mode.index}: #{mode.red:02X}{mode.green:02X}{mode.blue:02X}, "
            f"brightness {mode.brightness}, wire speed {mode.wire_speed}"
        )
    return 0


def _parse_rgb(value: str) -> tuple[int, int, int]:
    return parse_rgb(value)


async def _set_color(
    value: str,
    address: str | None,
    timeout: float,
    dry_run: bool,
    delay: float,
    direct: bool,
) -> int:
    red, green, blue = _parse_rgb(value)
    if dry_run:
        print(encode_static_color(red, green, blue).hex(" ").upper())
        return 0
    if not direct:
        if address is not None or delay != 0:
            raise ValueError("--device and --delay require --direct")
        request_color(value)
        print(f"Queued {value.upper()}")
        return 0
    timeout = _positive_float(timeout, "timeout")
    delay = _nonnegative_float(delay, "delay")
    with ownership_lock(blocking=False):
        if _daemon_is_active():
            raise ValueError("stop or release the QR65 daemon before using --direct")
        device = address
        if address is None:
            devices = await discover(timeout)
            if len(devices) != 1:
                print(f"Expected one QR65 advertisement, found {len(devices)}.")
                return 1
            device = devices[0].device
        assert device is not None
        brightness, packet = await set_static_color(
            device, red, green, blue, timeout, delay
        )
    print(f"Set {value.upper()} at brightness {brightness}: {packet.hex(' ').upper()}")
    return 0


def _control_daemon(action: str) -> None:
    """Start or stop only the QR65 user service."""
    with _control_lock():
        if action == "stop":
            subprocess.run(
                ["/usr/bin/systemctl", "--user", "stop", SERVICE_UNIT],
                check=True, capture_output=True, text=True, timeout=15,
            )
            runtime = read_runtime_status()
            write_runtime_status(
                "released",
                runtime["appliedColor"],
                "BLE released. Connect the phone to QR65 Bluetooth audio, then open ConneX.",
                applied_brightness=runtime["appliedBrightness"],
            )
            return
        was_released = read_runtime_status()["connection"] == "released"
        subprocess.run(
            ["/usr/bin/systemctl", "--user", "start", SERVICE_UNIT],
            check=True, capture_output=True, text=True, timeout=15,
        )
        if was_released:
            deadline = time.monotonic() + 2
            while (
                read_runtime_status()["connection"] == "released"
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the QR65 command-line interface."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "scan":
            return asyncio.run(_scan(args.timeout, args.all))
        if args.command == "inspect":
            return asyncio.run(_inspect(args.device, args.timeout))
        if args.command == "query-light":
            return asyncio.run(_query_light(args.device, args.timeout))
        if args.command == "set-color":
            return asyncio.run(
                _set_color(
                    args.color,
                    args.device,
                    args.timeout,
                    args.dry_run,
                    args.delay,
                    args.direct,
                )
            )
        if args.command == "api-version":
            value = {"apiVersion": 1, "daemonVersion": __version__, "statusVersion": 1}
            if args.as_json:
                print(json.dumps(value, separators=(",", ":")))
            else:
                print(f"Consumer API: {value['apiVersion']}")
                print(f"Daemon: {value['daemonVersion']}")
                print(f"Status schema: {value['statusVersion']}")
            return 0
        if args.command == "mode":
            if args.mode == "dynamic":
                result = set_dynamic_mode(args.color)
                print(f"Mode dynamic; queued {result.color}")
            else:
                normalized = set_static_mode(args.color)
                print(f"Mode static; queued {normalized}")
            return 0
        if args.command == "sync":
            result = sync_desired()
            print(f"Queued {result.color}")
            return 0
        if args.command == "brightness":
            value = set_brightness(args.percent)
            print(f"Brightness queued at {value}%")
            return 0
        if args.command == "color-matching":
            enabled = set_color_matching(args.state == "on")
            print(f"Color matching {'enabled' if enabled else 'disabled'}")
            return 0
        if args.command == "release":
            _control_daemon("stop")
            print("BLE released to ConneX")
            return 0
        if args.command == "resume":
            _control_daemon("start")
            print("QR65 daemon resumed")
            return 0
        if args.command == "status":
            value = build_status(load_config())
            if args.as_json:
                print(json.dumps(value, separators=(",", ":")))
            else:
                print(f"Mode: {value['mode']}")
                print(f"Color matching: {'on' if value['colorMatching'] else 'off'}")
                configured_brightness = value["configuredBrightness"]
                print(f"Brightness (configured): {configured_brightness if configured_brightness is not None else 'preserve device'}")
                print(f"Connection: {value['connection']}")
                print(f"Requested (queued): {value['requestedColor'] or 'none'} ({value['requestedSource'] or 'unknown'})")
                print(f"Applied (device confirmed): {value['appliedColor'] or 'none'}")
                brightness = value["appliedBrightness"]
                print(f"Brightness (device confirmed): {brightness if brightness is not None else 'unknown'}")
                if value["message"]:
                    print(f"Message: {value['message']}")
            return 0
        if args.command == "daemon":
            try:
                asyncio.run(daemon.run())
            except KeyboardInterrupt:
                pass
            return 0
    except (BleakError, ConnectionError, OSError, RuntimeError, subprocess.SubprocessError,
            TimeoutError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

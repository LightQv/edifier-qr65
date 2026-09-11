"""Persistent QR65 BLE session used while the speaker plays wired audio."""

from __future__ import annotations

import asyncio
import logging

from bleak.exc import BleakError

from .ble import ColorApplicationError, QR65Connection, discover
from .color import match_rgb
from .config import load_config
from .protocol import QR65_STATIC_MODE
from .status import MAX_MESSAGE_SIZE, write_runtime_status
from .desired import Request, ownership_lock, read_request

LOG = logging.getLogger(__name__)
_sleep = asyncio.sleep


async def _run_owned() -> None:
    """Control the QR65 while the process owns the cross-process BLE lock."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    last_request: Request | None = None
    last_applied: tuple[int, int, int] | None = None
    last_brightness: int | None = None
    last_error = ""
    blocked_request: tuple[int, tuple[int, int, int], int | None, bool] | None = None
    heartbeat_connection = "starting"
    heartbeat_applied: tuple[int, int, int] | None = None
    heartbeat_message = ""

    def report(connection: str, applied: tuple[int, int, int] | None = None, message: str = "") -> None:
        nonlocal heartbeat_connection, heartbeat_applied, heartbeat_message
        message = message[:MAX_MESSAGE_SIZE]
        heartbeat_connection = connection
        heartbeat_applied = applied
        heartbeat_message = message
        try:
            color = None if applied is None else "#%02X%02X%02X" % applied
            write_runtime_status(
                connection, color, message, applied_brightness=last_brightness
            )
        except OSError as error:
            LOG.warning("cannot write daemon status: %s", error)

    async def heartbeat() -> None:
        while True:
            await _sleep(5)
            report(heartbeat_connection, heartbeat_applied, heartbeat_message)

    report("starting", last_applied)
    heartbeat_task = asyncio.create_task(heartbeat())
    owner_task = asyncio.current_task()
    if owner_task is not None:
        owner_task.add_done_callback(lambda _task: heartbeat_task.cancel())
    while True:
        try:
            report("scanning", last_applied, last_error)
            devices = await discover(5)
            if len(devices) != 1:
                report(
                    "activation-required",
                    last_applied,
                    message="Switch to Bluetooth input and connect a paired Bluetooth audio host"
                    + (f"; last error: {last_error}" if last_error else ""),
                )
                await asyncio.sleep(3)
                continue

            report("connecting", last_applied, last_error)
            async with QR65Connection(devices[0].device, 10) as connection:
                _support, _ambient_frame, ambient = await connection.initialize()
                static = next(
                    (mode for mode in ambient.modes if mode.index == QR65_STATIC_MODE),
                    None,
                )
                if static is None:
                    raise RuntimeError("QR65 did not report static lighting mode 7")
                last_brightness = static.brightness
                last_error = ""

                LOG.info("BLE control connected")
                applied: tuple[int, int, int] | None = None
                applied_request: tuple[
                    int, tuple[int, int, int], int | None, bool
                ] | None = None
                while connection.client.is_connected:
                    try:
                        request = read_request()
                        if request is not None:
                            last_request = request
                    except (OSError, UnicodeError, ValueError) as error:
                        LOG.warning("cannot read requested color: %s", error)
                        request = last_request
                    requested = (
                        None if request is None else tuple(bytes.fromhex(request.color[1:]))
                    )
                    config = load_config()
                    desired_brightness = config.brightness
                    desired = None if requested is None else (
                        request.updated_at,
                        requested,
                        desired_brightness,
                        config.color_matching,
                    )
                    if desired is not None and desired == blocked_request:
                        report("error", applied, last_error)
                        try:
                            await asyncio.wait_for(connection.disconnected.wait(), timeout=1)
                        except TimeoutError:
                            continue
                        break
                    if requested is not None and desired != applied_request:
                        output = match_rgb(*requested) if config.color_matching else requested
                        try:
                            last_brightness, _packet = await connection.apply_static_color(
                                *output, brightness=desired_brightness
                            )
                        except ColorApplicationError as error:
                            blocked_request = desired
                            last_error = str(error)
                            LOG.warning("request blocked after failed confirmation: %s", error)
                            report("error", applied, last_error)
                            continue
                        applied = output
                        applied_request = desired
                        blocked_request = None
                        last_error = ""
                        last_applied = output
                        LOG.info(
                            "applied #%02X%02X%02X at %d%% for requested #%02X%02X%02X",
                            *output, last_brightness, *requested,
                        )
                    report("connected", applied)
                    try:
                        await asyncio.wait_for(connection.disconnected.wait(), timeout=1)
                    except TimeoutError:
                        continue
        except (BleakError, ConnectionError, TimeoutError, RuntimeError, ValueError) as error:
            LOG.warning("control session unavailable: %s", error)
            last_error = str(error)
            report("error", last_applied, message=last_error)
            await asyncio.sleep(3)


async def run() -> None:
    """Acquire BLE ownership and run the persistent controller."""
    with ownership_lock():
        await _run_owned()

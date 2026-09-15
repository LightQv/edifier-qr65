"""Persistent QR65 BLE session used while the speaker plays wired audio."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager

from bleak.exc import BleakError

from .ble import ColorApplicationError, QR65Connection, discover
from .color import match_rgb
from .config import load_config
from .protocol import QR65_STATIC_MODE
from .status import MAX_MESSAGE_SIZE, write_runtime_status
from .desired import Request, notification_socket_file, ownership_lock, read_request

LOG = logging.getLogger(__name__)
_sleep = asyncio.sleep
HEARTBEAT_SECONDS = 30
REQUEST_POLL_SECONDS = 5


@contextmanager
def _wakeup_socket() -> Iterator[socket.socket]:
    """Bind the best-effort local notification socket for queued changes."""
    path = notification_socket_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        listener.bind(str(path))
        os.chmod(path, 0o600)
        listener.setblocking(False)
        yield listener
    finally:
        listener.close()
        path.unlink(missing_ok=True)


async def _wait_for_change(
    listener: socket.socket, disconnected: asyncio.Event
) -> bool:
    """Wait for a local change, disconnect, or fallback poll deadline."""
    notified = asyncio.create_task(asyncio.get_running_loop().sock_recv(listener, 1))
    lost = asyncio.create_task(disconnected.wait())
    tasks = (notified, lost)
    try:
        done, _pending = await asyncio.wait(
            tasks, timeout=REQUEST_POLL_SECONDS, return_when=asyncio.FIRST_COMPLETED
        )
        return lost in done
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


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
    last_report: tuple[str, tuple[int, int, int] | None, str, int | None] | None = None

    def report(
        connection: str,
        applied: tuple[int, int, int] | None = None,
        message: str = "",
        *,
        force: bool = False,
    ) -> None:
        nonlocal heartbeat_connection, heartbeat_applied, heartbeat_message, last_report
        message = message[:MAX_MESSAGE_SIZE]
        heartbeat_connection = connection
        heartbeat_applied = applied
        heartbeat_message = message
        current = (connection, applied, message, last_brightness)
        if current == last_report and not force:
            return
        try:
            color = None if applied is None else "#%02X%02X%02X" % applied
            write_runtime_status(
                connection, color, message, applied_brightness=last_brightness
            )
            last_report = current
        except OSError as error:
            LOG.warning("cannot write daemon status: %s", error)

    owner_task = asyncio.current_task()

    async def heartbeat() -> None:
        while True:
            await _sleep(HEARTBEAT_SECONDS)
            if owner_task is None or owner_task.cancelling():
                return
            report(heartbeat_connection, heartbeat_applied, heartbeat_message, force=True)

    report("starting", last_applied)
    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        with _wakeup_socket() as listener:
            while True:
                try:
                    report("scanning", last_applied, last_error)
                    scan_started = time.monotonic()
                    devices = await discover(5)
                    LOG.info("BLE scan completed in %.3fs", time.monotonic() - scan_started)
                    if len(devices) != 1:
                        report(
                            "activation-required",
                            last_applied,
                            message=(
                                "Switch to Bluetooth input and connect a paired Bluetooth audio host"
                                + (f"; last error: {last_error}" if last_error else "")
                            ),
                        )
                        await asyncio.sleep(3)
                        continue

                    report("connecting", last_applied, last_error)
                    connection_started = time.monotonic()
                    async with QR65Connection(devices[0].device, 10) as connection:
                        _support, _ambient_frame, ambient = await connection.initialize()
                        static = next(
                            (
                                mode
                                for mode in ambient.modes
                                if mode.index == QR65_STATIC_MODE
                            ),
                            None,
                        )
                        if static is None:
                            raise RuntimeError("QR65 did not report static lighting mode 7")
                        last_brightness = static.brightness
                        last_error = ""

                        LOG.info(
                            "BLE control connected and initialized in %.3fs",
                            time.monotonic() - connection_started,
                        )
                        applied: tuple[int, int, int] | None = None
                        applied_request: tuple[
                            int, tuple[int, int, int], int | None, bool
                        ] | None = None
                        initial_state = ambient
                        while connection.client.is_connected:
                            try:
                                request = read_request()
                                if request is not None:
                                    last_request = request
                            except (OSError, UnicodeError, ValueError) as error:
                                LOG.warning("cannot read requested color: %s", error)
                                request = last_request
                            requested = (
                                None
                                if request is None
                                else tuple(bytes.fromhex(request.color[1:]))
                            )
                            config = load_config()
                            desired_brightness = config.brightness
                            desired = (
                                None
                                if requested is None
                                else (
                                    request.updated_at,
                                    requested,
                                    desired_brightness,
                                    config.color_matching,
                                )
                            )
                            if desired is not None and desired == blocked_request:
                                report("error", applied, last_error)
                                if await _wait_for_change(
                                    listener, connection.disconnected
                                ):
                                    break
                                continue
                            if requested is not None and desired != applied_request:
                                output = (
                                    match_rgb(*requested)
                                    if config.color_matching
                                    else requested
                                )
                                try:
                                    apply_started = time.monotonic()
                                    state = initial_state
                                    initial_state = None
                                    last_brightness, _packet = (
                                        await connection.apply_static_color(
                                            *output,
                                            brightness=desired_brightness,
                                            state=state,
                                        )
                                    )
                                except ColorApplicationError as error:
                                    blocked_request = desired
                                    last_error = str(error)
                                    applied = None
                                    last_applied = None
                                    last_brightness = None
                                    LOG.warning(
                                        "request blocked after failed confirmation: %s",
                                        error,
                                    )
                                    report("error", applied, last_error)
                                    continue
                                applied = output
                                applied_request = desired
                                blocked_request = None
                                last_error = ""
                                last_applied = output
                                LOG.info(
                                    "applied #%02X%02X%02X at %d%% for requested "
                                    "#%02X%02X%02X in %.3fs",
                                    *output,
                                    last_brightness,
                                    *requested,
                                    time.monotonic() - apply_started,
                                )
                            report("connected", applied)
                            initial_state = None
                            if await _wait_for_change(
                                listener, connection.disconnected
                            ):
                                break
                except (
                    BleakError,
                    ConnectionError,
                    TimeoutError,
                    RuntimeError,
                    ValueError,
                ) as error:
                    LOG.warning("control session unavailable: %s", error)
                    last_error = str(error)
                    report("error", last_applied, message=last_error)
                    await asyncio.sleep(3)
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)


async def run() -> None:
    """Acquire BLE ownership and run the persistent controller."""
    with ownership_lock():
        await _run_owned()

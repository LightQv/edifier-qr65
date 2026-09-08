# Edifier QR65 Omarchy Theme Sync

Unofficial Linux BLE control for the Edifier QR65 ambient lights. A user daemon
holds the QR65 control connection while audio continues over a wired input.
Dynamic mode follows the active Omarchy theme `accent`; Static mode holds a
selected color.

## Confirmed Environment

- Edifier QR65 global model
- EDIFIER ConneX Android `1.0.30`
- BlueZ through Bleak `3.0.2`
- Omarchy `4.0.2-1` with PipeWire analog output
- QR65 lighting array `4`, static mode `7`

The speaker firmware version was not exposed during testing. Other firmware
versions may behave differently. The unpublished `EDF QR65` variant is
intentionally rejected because its lighting array and mode mapping have not
been verified.

## Hardware Constraint

The tested QR65 advertises its BLE control service and Edifier manufacturer
data only while a Bluetooth
Classic connection is active in Bluetooth input mode. Once BLE is connected,
the connection survives switching the speaker back to its wired input.

After a speaker power cycle, service restart, or lost BLE connection:

1. Switch the QR65 to Bluetooth input.
2. Let a previously paired phone connect, with ConneX closed.
3. Wait for the daemon to connect and apply the current color.
4. Switch the QR65 back to the wired input.

The daemon then remains connected and later theme changes do not interrupt
wired audio. ConneX and the Linux daemon cannot hold the BLE connection at the
same time.

## Installed Components

```text
~/.local/bin/edifier-qr65
~/.local/share/edifier-qr65/venv/
~/.config/systemd/user/edifier-qr65.service
~/.config/omarchy/hooks/theme-set.d/qr65-theme-sync
~/.config/omarchy/plugins/lightqv.edifier-qr65/
~/.config/edifier-qr65/config.toml
~/.local/state/edifier-qr65/color
~/.local/state/edifier-qr65/request.json
~/.local/state/edifier-qr65/status.json
~/.local/state/edifier-qr65/operation.lock
```

The command points to a dedicated virtual environment outside the plugin Git
checkout. The systemd unit and theme hook are installed as physical files.

## Usage

Select Dynamic mode and immediately resolve the current theme accent:

```bash
edifier-qr65 mode dynamic
```

Select Static mode, persist its fallback color, and queue it:

```bash
edifier-qr65 mode static '#89B4FA'
```

Reapply the desired color for the configured mode and inspect queued versus
daemon-reported state:

```bash
edifier-qr65 sync
edifier-qr65 status
edifier-qr65 status --json
```

Temporarily release the speaker's single BLE control connection to Edifier
ConneX, then resume the daemon after fully closing the app:

```bash
edifier-qr65 release
# Connect the phone to QR65 Bluetooth audio, then open ConneX.
edifier-qr65 resume
```

`release` stops the user service cleanly and preserves a non-expiring handoff
status. `resume` starts the service without changing the configured mode or
requested color. The normal Bluetooth-input activation flow may be required
before Linux can reclaim BLE.

Set persistent LED brightness or return to literal RGB output:

```bash
edifier-qr65 brightness 50
edifier-qr65 color-matching off
edifier-qr65 color-matching on
```

Until brightness is explicitly set, the daemon preserves the value read from
the speaker. Brightness changes are applied through the existing static-light
packet and confirmed by post-write device readback.

Dynamic mode queues the validated theme accent. If bounded accent resolution
fails, it temporarily queues the configured static color while preserving
Dynamic mode so a later theme change recovers automatically. Theme hooks are a
successful no-op in Static mode.

Queued commands use an advisory process lock so mode configuration and its
desired-color request cannot interleave. `request.json` is the authoritative
desired state; the plain `color` file is maintained only for compatibility with
daemon processes that loaded the older backend.

The legacy direct queue remains available for compatibility:

```bash
edifier-qr65 set-color '#89B4FA'
```

Queue the current Omarchy accent:

```bash
edifier-qr65 theme-sync
```

`theme-sync` follows Dynamic fallback rules and is a no-op in Static mode.
`status --json` does not perform Bluetooth discovery or writes. Its stable keys
are `version`, `mode`, `configuredStaticColor`, `configuredBrightness`,
`colorMatching`, `requestedColor`, `requestedSource`, `appliedColor`,
`appliedBrightness`, `connection`, `message`, and `updatedAt`. The new fields
are additive to schema version `1`; older runtime files remain valid.
Runtime connection values are `starting`, `scanning`, `activation-required`,
`connecting`, `connected`, `released`, and `error`; a heartbeat older than 15
seconds is reported as `error` rather than falsely claiming a live connection.
The explicit `released` handoff state does not expire while the daemon is
stopped.
`requestedColor` is the display target. `appliedColor` is the actual QR65 RGB
command confirmed by a post-write lighting-state query, so the values differ
while color matching is enabled. Before each write, the daemon also queries the
live state to verify the held GATT session and either preserve or update the
speaker's static-mode brightness.
If a write cannot be confirmed, the daemon blocks that request rather than
repeating hardware writes indefinitely. Change a control or use Reapply Color
to issue a new request.
The QR65 LEDs do not visually match a color-managed display for every literal
RGB value. The optional matching profile uses 28 chromatic target-to-ConneX
measurements collected at 50% brightness; four neutral observations were
excluded because the QR65 retained a blue cast at every attempted command. Its
regularized hue-specific model preserves literal neutral RGB by design and maps
`#E68E0D` to approximately `#FD3600`. Literal RGB remains the default until the
fitted profile has passed live visual A/B testing. See `PROTOCOL.md` for the
confirmed ConneX/daemon comparison and profile limitations.

To collect a display-to-light profile, open `calibration/index.html` in a
color-managed browser and follow `calibration/README.md`. The page records 24
fitting colors and eight withheld validation colors at 50% brightness, saves
progress locally, and exports the target-to-ConneX measurements as JSON. Keep
color matching disabled while collecting measurements.

## Omarchy Plugin

The top-bar widget is placed immediately before the Bluetooth widget. Open it
by clicking its glow icon or pressing `SUPER+CTRL+G`.

The native-style panel provides Follow Theme and Static Color modes, eight
preset colors, validated hexadecimal input, brightness, screen matching, and
recovery guidance. The hero switch controls daemon ownership: on gives BLE to
the daemon; off releases it for ConneX. It supports arrows or `h/j/k/l`, Enter
or Space, `/` for the hex editor while in Static Color mode, Escape to close,
and Tab or Shift+Tab to move between neighboring bar panels.

The repository root is the plugin source. `omarchy plugin add` clones it under
`~/.config/omarchy/plugins/lightqv.edifier-qr65/`.

Inspect discovery and current lighting state while ConneX is closed:

```bash
edifier-qr65 scan
edifier-qr65 inspect
edifier-qr65 query-light
```

Generate a packet without Bluetooth activity:

```bash
edifier-qr65 set-color '#123456' --dry-run
```

Perform a direct one-shot write only when the daemon is stopped and BLE is
advertising:

```bash
systemctl --user stop edifier-qr65
edifier-qr65 set-color '#123456' --direct
systemctl --user start edifier-qr65
```

Supplying `--device` never bypasses this gate. Direct writes first verify the
tested global-model GATT service and query array `4` with static mode `7`.
They are refused while the QR65 user service is active.

## Service

```bash
systemctl --user status edifier-qr65
journalctl --user -u edifier-qr65 -f
systemctl --user restart edifier-qr65
```

Normal log messages include:

```text
connected; switch the QR65 to wired input when ready
applied #89B4FA
```

When the service is scanning but cannot connect, briefly use the Bluetooth-mode
procedure described above.

## Development

Runtime dependencies are Python 3.12 or newer, BlueZ, `python-bleak`, systemd
user services, Omarchy Quattro, and Quickshell. NumPy is required only to refit
the optional calibration profile and can be installed with
`pip install '.[calibration]'` in a development environment.
The service uses the standard `~/.config` and `~/.local/state` locations for
its sandboxed writable directories.

Run checks with:

```bash
python -m pytest -q
python -m compileall -q src tests
bash -n hooks/qr65-theme-sync
bash -n install.sh uninstall.sh
systemd-analyze --user verify systemd/edifier-qr65.service
omarchy plugin validate .
```

## Installation

Install the external BLE dependency, add the Git repository as an Omarchy
plugin, then install its backend:

```bash
omarchy pkg add python-bleak
omarchy plugin add https://github.com/LightQv/omarchy-edifier-qr65.git --yes
cd "$HOME/.config/omarchy/plugins/lightqv.edifier-qr65"
./install.sh
edifier-qr65 mode dynamic
```

The installer is idempotent. It refuses to replace unrelated command, service,
or hook files unless `--force` is explicitly supplied. It does not modify
Hyprland configuration. To add the optional `SUPER+CTRL+G` shortcut, add this
line to `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + CTRL + G", "QR65 glow", "omarchy-shell shell toggle lightqv.edifier-qr65")
```

After `omarchy plugin update lightqv.edifier-qr65`, rerun `./install.sh` to
refresh the backend, service, and hook. A daemon restart can require the normal
Bluetooth activation cycle.

## Uninstall

```bash
cd "$HOME/.config/omarchy/plugins/lightqv.edifier-qr65"
./uninstall.sh
cd
omarchy plugin remove lightqv.edifier-qr65
```

Remove the `SUPER+CTRL+G` QR65 binding from `~/.config/hypr/bindings.lua` when
uninstalling the plugin.

The uninstaller preserves `~/.config/edifier-qr65` and
`~/.local/state/edifier-qr65`. Remove those separately only if the saved
lighting settings and state are no longer needed.

## Safety

Only the captured support query (`0xD8`), ambient-light query (`0x6A`), and
array-4 static-color set (`0x6B`) are transmitted. The CLI does not expose raw
packet writes, firmware operations, power controls, or command probing.

See `PROTOCOL.md` for sanitized protocol evidence and known limitations.

## License

This project is available under the MIT License. See `LICENSE`.

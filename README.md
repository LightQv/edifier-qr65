# Edifier QR65 BLE Daemon and CLI

Unofficial Linux control of the Edifier QR65 ambient lights over Bluetooth Low
Energy (BLE). A persistent systemd user service holds the QR65 control
connection so lighting can be changed while audio continues over a wired input.

This repository is self-contained and Omarchy-independent. External programs
may use its versioned CLI/JSON API to supply colors, but the daemon does not
install, update, remove, or otherwise manage those consumers. The
[Omarchy QR65 plugin](https://github.com/LightQv/omarchy-edifier-qr65) is one
optional consumer.

After installing this daemon, Omarchy users can add and enable that consumer
separately:

```bash
omarchy plugin add https://github.com/LightQv/omarchy-edifier-qr65.git --enable
```

## Confirmed Hardware and Software

The implementation and protocol safety boundary were confirmed with:

- Edifier QR65 global model
- EDIFIER ConneX Android `1.0.30` (`versionCode 70`)
- BlueZ through Bleak `3.0.2`
- PipeWire analog output
- QR65 lighting array `4`, static mode `7`, and protocol V2 without payload
  encryption

The speaker firmware version was not exposed during testing, so other firmware
may behave differently. The unpublished `EDF QR65` variant is intentionally
rejected because its service, lighting array, and mode mapping have not been
verified.

## Hardware Connection Constraint

On the tested QR65, cold activation after a speaker power cycle required:

1. The speaker is using Bluetooth input.
2. A Bluetooth Classic audio connection is active.

After BLE connects, that connection survives switching the speaker back to a
wired input and does not interrupt analog playback. A warm speaker also allowed
a fresh BLE connection without Classic audio, but this did not survive a power
cycle and is not a reliable cold-start procedure. The Classic connection does
not need to be Linux's default audio output.

Pairing, audio connection, codecs, and output routing remain the user's and
operating system's responsibility; the daemon manages only BLE lighting
control. This constraint is why it keeps one persistent GATT session instead of
reconnecting for every color.

After a speaker power cycle, service restart, or lost BLE connection:

1. Close ConneX if it is open.
2. Switch the QR65 to Bluetooth input.
3. Connect any previously paired Bluetooth audio host, such as the computer or
   a phone. ConneX is not required.
4. Wait for `edifier-qr65 status` to report `connected`.
5. Switch the QR65 back to the wired input.

Alternatively, leave the QR65 on Bluetooth input and let the operating system
reconnect its paired audio endpoint normally. Tests on the current host
confirmed automatic audio and BLE recovery after speaker power cycles and
computer boots. The daemon does not initiate or configure the audio connection;
once BLE becomes available, its retry loop discovers and controls it.

Cold-starting the tested speaker on RCA did not expose either its BLE controller
or Classic audio endpoint to Linux or ConneX. No software-only RCA activation
path is currently known.

ConneX and the Linux daemon cannot own the QR65 BLE connection simultaneously.
Use `release` and `resume` for an intentional handoff.

## Requirements

- Linux with BlueZ
- Python 3.12 or newer
- `python-bleak` available to the system Python
- systemd user services
- `python`, `systemctl`, and `sha256sum` on `PATH`

Install `python-bleak` with the operating system's package manager before
running the installer. The managed virtual environment uses system site
packages and the installer deliberately does not download runtime dependencies.

## Install, Update, and Uninstall

The scripts in this repository own only the daemon, CLI launcher, and systemd
unit. Run them from a daemon repository checkout:

```bash
git clone https://github.com/LightQv/edifier-qr65.git
cd edifier-qr65
./install.sh
```

The installer builds a wheel, installs it into a dedicated virtual environment,
records ownership checksums, enables the user service, and restarts it. It is
idempotent and refuses to replace unrelated or locally modified managed files.
Use `./install.sh --force` only after inspecting the reported conflict.

Update the daemon from the same checkout:

```bash
git pull --ff-only
./install.sh
```

The restart may require the Bluetooth-input activation procedure above.

Uninstall daemon-owned components with:

```bash
./uninstall.sh
```

The uninstaller verifies its ownership marker and managed-file checksums before
removal. It stops and disables the service, then removes the daemon environment,
launcher, unit, and ownership marker. User configuration and runtime state are
preserved; remove those directories manually only if their saved values are no
longer wanted.

## Installed Paths

With the standard XDG locations, installation and runtime use:

```text
~/.local/bin/edifier-qr65                         CLI symlink
~/.local/share/edifier-qr65/releases/             immutable Python environments
~/.local/share/edifier-qr65/current               active release symlink
~/.local/share/edifier-qr65/install-state         ownership/checksum marker
~/.config/systemd/user/edifier-qr65.service       managed user unit
~/.config/edifier-qr65/config.toml                 persistent settings
~/.local/state/edifier-qr65/request.json           authoritative desired color
~/.local/state/edifier-qr65/color                  legacy compatibility mirror
~/.local/state/edifier-qr65/status.json            daemon heartbeat/status
~/.local/state/edifier-qr65/operation.lock         queued-operation lock
~/.local/state/edifier-qr65/ble.lock               BLE ownership lock
~/.local/state/edifier-qr65/control.lock           lifecycle-operation lock
~/.local/state/edifier-qr65/notify.sock            best-effort daemon wakeup
```

Lock and state files are created on demand. Custom XDG data, config, and state
locations are rejected because the supplied systemd unit binds only these
standard managed paths into its private home namespace.

## Service Use

The installer enables and starts `edifier-qr65.service`. Manage and inspect it
with normal user-service commands:

```bash
systemctl --user status edifier-qr65
systemctl --user restart edifier-qr65
journalctl --user -u edifier-qr65 -f
```

Typical log messages include scan and connection timing plus `applied #89B4FA
at 50% for requested #89B4FA in 0.234s`. If status remains
`activation-required`, repeat the Bluetooth-input activation procedure.

The unit hides the home directory except for a read-only bind of its managed
environment and writable binds for its configuration and state paths. The
system is read-only and the process cannot gain new privileges.

## CLI Lighting Controls

Every color argument is a strict six-digit `#RRGGBB` value. Quote it in a shell
because `#` otherwise begins a comment.

### Dynamic mode

Dynamic mode is externally driven. Selecting it **requires an explicit color**;
the daemon does not discover a desktop theme or choose a color source:

```bash
edifier-qr65 mode dynamic '#89B4FA'
```

This atomically persists Dynamic mode and queues the supplied color. A consumer
must issue the command again whenever its source color changes. The durable
request remains authoritative; a local Unix datagram wakes the daemon
immediately, with periodic polling as a fallback if a notification is missed.

### Static mode

Static mode persists and queues its own fixed color:

```bash
edifier-qr65 mode static '#FFB86C'
```

### Sync and direct queueing

Requeue the configured static color, or the most recently requested Dynamic
color, without changing modes:

```bash
edifier-qr65 sync
```

`request.json` is authoritative desired state. Configuration and request writes
share an advisory lock so concurrent consumers cannot split a mode change from
its color. The lower-level compatibility command queues a color without changing
the configured mode:

```bash
edifier-qr65 set-color '#89B4FA'
```

### Brightness

Set persistent brightness from 0 through 100 percent:

```bash
edifier-qr65 brightness 50
```

Until brightness is explicitly configured, the daemon preserves the static-mode
brightness read from the speaker. Each change uses the static-light packet and
is confirmed by a post-write lighting-state query.

### Color matching

Literal RGB output is the default. Toggle the optional built-in matching profile
with:

```bash
edifier-qr65 color-matching on
edifier-qr65 color-matching off
```

With matching enabled, `requestedColor` remains the consumer's display target
while `appliedColor` reports the transformed RGB confirmed on the QR65. The
`subjective-v1` profile uses 12 saturated hues, three repeats, compensated
white, and three pastel preferences, measured at speaker brightness 50%,
monitor 75%, and night light disabled. It favors recognizable hue over literal
desaturation.
White maps to `#FFE080`; very light colors at or below 10% HSV saturation use
that neutral-white command, and colors from 10% through 20% transition smoothly
into the chromatic model. Black remains black. Orange `#E68E0D` maps to
`#E64003`, and mauve `#CBA6F7` to `#C244C0`. The user preferred this profile on
three additional pastel accents and the original orange regression target.
Small saturation differences remain; dark targets and the full brightness range
are not extensively characterized. Literal RGB remains the default. See the method in
[`calibration/README.md`](calibration/README.md) and evidence in
[`calibration/OBSERVATIONS.md`](calibration/OBSERVATIONS.md).

### Release and resume

Temporarily hand the single BLE connection to ConneX, then reclaim it after
fully closing the app:

```bash
edifier-qr65 release
# Keep a paired audio host connected if ConneX cannot see the speaker.
edifier-qr65 resume
```

`release` cleanly stops only the QR65 user service and writes a non-expiring
`released` status. The service remains enabled, so this handoff is temporary:
it starts again at the next user login/reboot, installer restart, or explicit
`resume`. `resume` starts only that service; neither command changes pairing,
audio routing, mode, brightness, matching, or requested color. Reclaiming BLE
may require the normal Bluetooth-input activation flow.

## Versioned Consumer API v1

External integrations should first query the API contract:

```bash
edifier-qr65 api-version
edifier-qr65 api-version --json
```

The JSON form is compact and has these exact keys:

```json
{"apiVersion":1,"daemonVersion":"0.1.0","statusVersion":1}
```

Consumer API version `1` consists of the explicit-color control commands
documented above and the status schema below. Consumers should reject an
unsupported `apiVersion` or `statusVersion` rather than inferring compatibility
from `daemonVersion`.

Read state without BLE discovery or writes:

```bash
edifier-qr65 status
edifier-qr65 status --json
```

Status schema version `1` always returns exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | integer | Status schema version; currently `1`. |
| `mode` | `"dynamic"` or `"static"` | Persisted lighting mode. |
| `configuredStaticColor` | string | Persisted uppercase `#RRGGBB` static color. |
| `configuredBrightness` | integer or `null` | Configured `0..100`; `null` preserves device brightness. |
| `colorMatching` | boolean | Whether the built-in matching transform is enabled. |
| `requestedColor` | string or `null` | Latest queued uppercase `#RRGGBB` display target. |
| `requestedSource` | string | Request provenance, normally `dynamic`, `static`, or `direct`; empty only for migrated legacy state or no request. |
| `appliedColor` | string or `null` | RGB command confirmed by device readback. |
| `appliedBrightness` | integer or `null` | Device-confirmed `0..100`, or unknown. |
| `connection` | string | One of the connection states listed below. |
| `message` | string | Operational or diagnostic detail; may be empty. |
| `updatedAt` | integer | Unix timestamp in seconds for the daemon status update, or `0` when unavailable. |

An example connected response is:

```json
{"version":1,"mode":"dynamic","configuredStaticColor":"#7DAEA3","configuredBrightness":null,"colorMatching":false,"requestedColor":"#89B4FA","requestedSource":"dynamic","appliedColor":"#89B4FA","appliedBrightness":50,"connection":"connected","message":"","updatedAt":1788940800}
```

Exact `connection` states are:

- `starting`: daemon initialization has begun.
- `scanning`: searching for the verified QR65 advertisement.
- `activation-required`: no single verified advertisement is available; use
  the Bluetooth-input activation flow with any paired audio host.
- `connecting`: opening and validating the GATT session.
- `connected`: the session is live and its heartbeat is current.
- `released`: the daemon was intentionally stopped for BLE handoff; this state
  does not expire.
- `error`: status is unavailable, malformed, stale, future-dated, or the daemon
  reported a control/application failure.

All states except `released` become `error` when their heartbeat is more than 60
seconds old. The daemon writes transitions immediately and refreshes unchanged
state every 30 seconds without forcing ephemeral status to stable storage. A
timestamp over five seconds in the future also becomes `error`.
If a write cannot be confirmed, the daemon blocks that exact request rather than
repeating hardware writes indefinitely, and reports applied color and brightness
as unknown because the hardware result is indeterminate. Change a control or run
`sync` to issue a new request.

## Diagnostics and One-Shot Operations

Start with status and service logs:

```bash
edifier-qr65 status --json
systemctl --user status edifier-qr65
journalctl --user -u edifier-qr65 --since today
```

For discovery or GATT inspection, release the daemon, close ConneX, activate BLE
advertising as described above, and run:

```bash
edifier-qr65 scan
edifier-qr65 inspect
edifier-qr65 query-light
```

`scan --all` includes unrelated BLE devices. `inspect` lists services and
characteristics without writing. `query-light` reads the support and ambient
lighting state without changing it. Both connection commands accept `--device`
and `--timeout`.

Generate the allowlisted static packet without Bluetooth activity:

```bash
edifier-qr65 set-color '#123456' --dry-run
```

Perform a direct one-shot write only while the daemon is stopped or released
and BLE is advertising:

```bash
edifier-qr65 release
edifier-qr65 set-color '#123456' --direct
edifier-qr65 resume
```

Supplying `--device` does not bypass the direct-write gate. Direct writes first
verify the tested global-model GATT service and query array `4`, static mode `7`.

## Calibration

To collect saturated hue observations, open `calibration/hue-pass.html` in a
color-managed browser and follow [`calibration/README.md`](calibration/README.md).
The page presents 12 hues and three repeat checks, stores progress locally, and
exports JSON. The accepted observations and qualitative comparisons are retained
alongside the tool; superseded experiments remain available through Git history.

Keep display conditions fixed, release BLE to ConneX, set static lighting to
exactly 50% brightness, and disable daemon color matching while measuring. To
reproduce the accepted profile and verify runtime agreement:

```bash
python calibration/model.py
PYTHONPATH=src python -m unittest discover -s calibration -p test_model.py
```

The calibration model and runtime use only the Python standard library.

## Migration from the Old Combined Installation

Running this repository's `./install.sh` over an installation made by the old
combined daemon/plugin repository performs an adoption when the existing marker
has owner `lightqv.edifier-qr65`. Before changing anything, it verifies the
recorded checksums of the existing systemd unit and old
`~/.config/omarchy/hooks/theme-set.d/qr65-theme-sync` hook. It then:

1. Reuses and updates the daemon virtual environment and launcher.
2. Installs the standalone service unit.
3. Removes the verified legacy theme hook.
4. Rewrites the marker with owner `edifier-qr65`.
5. Enables and restarts the standalone daemon.

If a recorded legacy file was modified or is unrecognized, adoption stops
without replacing it; inspect the file before considering `--force`. Adoption
does not modify or remove any plugin checkout, widget, shell configuration, or
optional consumer. Manage those separately in their own repository.

Existing `config.toml`, `request.json`, status, and color state remain in place.
On first use without a configuration file, a valid legacy plain `color` value is
adopted as the initial static fallback. New readers prefer `request.json`; the
plain `color` file remains only as a compatibility mirror for older daemon
processes during migration.

## Safety

The implementation transmits only the captured and verified operations:

```text
0xD8  support-function query
0x6A  ambient-light query
0x6B  array-4, mode-7 static RGB write
```

The CLI does not expose raw packet writes, command probing, unsupported lighting
modes, input selection, power, reset, charging, volume, OTA, or firmware
operations. Writes use freshly initialized or newly queried live state to
validate the held session and preserve or set brightness, then use a post-write
query to confirm the resulting RGB. The first write after connecting reuses the
state read during initialization instead of immediately repeating that query.
See [`PROTOCOL.md`](PROTOCOL.md) for sanitized protocol evidence and known
limitations.

## Development Checks

Install the project's test and build dependencies in a development environment,
then run:

```bash
python -m pytest -q
python -m compileall -q src tests
bash -n install.sh uninstall.sh
shellcheck install.sh uninstall.sh
systemd-analyze --user verify systemd/edifier-qr65.service
python -m build
```

The systemd verification expects the managed environment's daemon executable to
exist; CI uses a temporary executable at that path.

## License

This project is available under the MIT License. See [`LICENSE`](LICENSE).

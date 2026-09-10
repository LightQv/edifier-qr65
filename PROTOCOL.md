# Edifier QR65 BLE Lighting Protocol

## Evidence

This document records behavior confirmed on a global Edifier QR65 using:

- EDIFIER ConneX Android `1.0.30` (`versionCode 70`)
- Static analysis of the installed base and split APKs
- Android full HCI snoop capture
- Linux BlueZ/Bleak discovery, query, write, and persistence tests

Device addresses are intentionally omitted.

## Advertisement

```text
Search UUID:     00005d00-0000-1000-8000-00805f9b34fb
Manufacturer ID: 0x07E0
```

The captured manufacturer payload ended with:

```text
02 00
```

ConneX interprets the penultimate byte as BLE protocol version and the final
byte as encryption mode. This QR65 therefore uses protocol V2 and no payload
XOR encryption.

The product catalog also contains an unpublished `EDF QR65` variant:

```text
Search UUID: 00003901-0000-1000-8000-00805f9b34fb
Service:     48093901-1a48-11e9-ab14-d663bd873d93
```

That variant was not tested.
The release implementation therefore does not discover or connect to that
variant automatically.

## GATT Layout

```text
Service: 48095d01-1a48-11e9-ab14-d663bd873d93
Read:    48090001-1a48-11e9-ab14-d663bd873d93 (read, notify)
Write:   48090002-1a48-11e9-ab14-d663bd873d93 (write, write without response)
```

ConneX requests MTU `512` for the global QR65 and enables notifications on the
read characteristic before issuing commands.

## Protocol V2 Frame

Host to device:

```text
AA EC <COMMAND> <LEN_HI> <LEN_LO> <PAYLOAD...> <CHECKSUM>
```

Device to host:

```text
BB EC <COMMAND> <LEN_HI> <LEN_LO> <PAYLOAD...> <CHECKSUM>
```

`CC` is also accepted by ConneX as a legacy receive header. The checksum is the
sum of every preceding transmitted byte modulo 256. Length is the payload size
as an unsigned big-endian 16-bit value.

## Initialization

ConneX initializes normal controls with support-function query `0xD8`:

```text
AA EC D8 00 00 6E
```

The tested QR65 response payload was:

```text
00 00 01 04 01 01 01 00 00 00 01 01 0A 12 0A 00 00 20 04 83 04 22
```

Only the ambient-light capability is currently used by this project; unrelated
capability bits are not interpreted.

## Ambient-Light Query

Command `0x6A` queries all light modes:

```text
AA EC 6A 00 00 00
```

Response payload:

```text
<ARRAY_INDEX> <SELECTED_MODE> <MODE_RECORD...>
```

For array `4`, each mode record is six bytes:

```text
<MODE> <RED> <GREEN> <BLUE> <BRIGHTNESS> <SPEED>
```

The tested QR65 reported:

```text
Array index: 4
Static mode: 7
Brightness: 50
Static speed: 255
```

ConneX resource mapping for array `4` labels mode `7` as `Static`.

## Static-Color Set

Command `0x6B` uses this seven-byte payload:

```text
04 07 <RED> <GREEN> <BLUE> <BRIGHTNESS> FF
```

The command is sent with ATT Write Command, without a GATT write response.
ConneX treats it as a no-response application command.

Captured examples:

```text
#FF2F15 at brightness 50
AA EC 6B 00 07 04 07 FF 2F 15 32 FF 87

#A0FF6C at brightness 50
AA EC 6B 00 07 04 07 A0 FF 6C 32 FF 4F

#3F51FF at brightness 50
AA EC 6B 00 07 04 07 3F 51 FF 32 FF D3
```

Linux live validation added:

```text
#FF0000 at brightness 50
AA EC 6B 00 07 04 07 FF 00 00 32 FF 43

#00FF00 at brightness 50
AA EC 6B 00 07 04 07 00 FF 00 32 FF 43
```

The speaker subsequently reported the same static-mode RGB values through
`0x6A`.

## Physical Color Rendering

A controlled ConneX/daemon comparison confirmed that both controllers leave
static mode `7` at literal `#E68E0D`, brightness `50`, and speed `255`. The LED
hardware rendered both identically, with a more yellow-green appearance than
the same CSS color on the desktop. A manually selected `#FF4000` looked closer
to the intended desktop orange on this speaker.

This is a physical gamut/calibration difference, not a preset command or RGB
encoding difference. The original model family was fitted from 20 subjective chromatic
target-to-ConneX matches and evaluated on eight withheld chromatic matches, all
collected at brightness `50`. Four neutral observations were excluded from
coefficient estimation because no tested RGB command removed the blue cast. A
saturation-scaled regularized radial-basis correction keeps neutral RGB
unchanged by design. Held-out command-space RMSE fell from `77.1` for raw RGB to `47.8`;
the final profile refits 28 chromatic observations and maps `#E68E0D` to
approximately `#FD3600`.

Nine fitting targets were explicitly marked outside the QR65's reproducible
gamut. Dark saturated colors could remain too bright even with a full-scale
command, and neutral colors retained a blue cast. The profile is subjective,
specific to the tested unit, display, viewing conditions, and 50% brightness;
it is not an instrument-measured physical characterization. Literal RGB remains
the default and live A/B fallback.

The second subjective pass supersedes that runtime model. It combines 12 saturated
hues, three repeats, a compensated white command `#FFE080`, and three pastel
preferences. White-command trials improved neutrality, correcting the earlier
decision to preserve neutral RGB unchanged. The runtime uses hue interpolation,
a saturation preference curve, and local pastel adjustments, with black preserved.
Orange `#E68E0D` now maps to `#E64003`. The user preferred the new profile over the
old one on three additional pastel accents and the original orange. Measurements
used speaker brightness 50%, monitor 75%, and disabled night light; one yellow
brightness check also retained hue at 25%. This does not establish uniform behavior
across all brightness levels. See `calibration/second-pass-observations.md`.

## Connection Constraint

Confirmed behavior:

1. BLE advertises while the QR65 is in Bluetooth input mode with a Bluetooth
   Classic connection.
2. BLE does not advertise while the phone is disconnected and wired input is
   active.
3. A BLE connection established in Bluetooth mode remains connected after the
   QR65 switches to wired input and its Classic phone connection drops.
4. Static-color writes over that held BLE connection do not interrupt active
   analog playback or change PipeWire's analog sink.

This is why the runtime uses a persistent daemon rather than connecting once
for every color-source change.

## Safety Boundary

The implementation allowlists only:

```text
0xD8  support-function query
0x6A  ambient-light query
0x6B  array-4, mode-7 static RGB write
```

Commands related to input selection, power, reset, OTA, firmware, charging,
volume, and unsupported lighting modes are not exposed.

## Remaining Unknowns

- Whether behavior changes on other QR65 firmware versions
- Whether the unpublished EDF QR65 uses the same array and mode mapping
- Whether a host-only method can trigger BLE advertising without a Classic
  connection and Bluetooth input mode
- Whether the QR65 eventually expires an otherwise idle held BLE connection
- An instrument-measured physical LED color profile across brightness levels

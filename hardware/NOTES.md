# Hardware Notes

## Before Wiring

Open the grow light base and measure the DC voltage on the LED driver
output. This will be either 12V or 24V. Write it down here:

**Grow light DC voltage:** ______ V

## Wiring Checklist (Phase 2)

- [ ] ESP32 A0 → wire → junction point
- [ ] Junction → 10kΩ resistor (R1) → GND
- [ ] Junction → MOSFET gate (G)
- [ ] MOSFET source (S) → GND
- [ ] MOSFET drain (D) → grow light GND wire
- [ ] Grow light V+ wire → power supply V+
- [ ] 1N4007 diode (D1) across drain-source: anode on source, cathode on drain
- [ ] ESP32 GND → power supply GND (common ground bus)

## Pin Identification

### STP55NF06L (TO-220, looking at the label side)
```
    ┌─────────┐
    │         │
    │ STP55   │
    │ NF06L   │
    │         │
    └─┬──┬──┬─┘
      │  │  │
      G  D  S
      1  2  3
```
Left to right: **Gate, Drain, Source**

### 1N4007 Diode
```
    band side = cathode (K)
    ───┤├───
    A      K
```
Cathode (band) connects to **drain** (higher voltage side).
Anode connects to **source** (ground side).

## Flash Log

### 2026-03-10 — CircuitPython 10.1.4

Firmware: `adafruit-circuitpython-adafruit_qtpy_esp32s3_nopsram-en_US-10.1.4.bin`
Source: https://circuitpython.org/board/adafruit_qtpy_esp32s3_nopsram/

```
Chip type:          ESP32-S3 (QFN56) (revision v0.2)
Features:           Wi-Fi, BT 5 (LE), Dual Core + LP Core, 240MHz,
                    Embedded Flash 4MB (XMC), Embedded PSRAM 2MB (AP_3v3)
Crystal frequency:  40MHz
MAC:                b4:3a:45:b0:dc:58
```

Bootloader mode: hold BOOT, tap RESET, release BOOT. Board goes dark (no LEDs).

Flash command:
```bash
esptool --port /dev/ttyACM0 --chip esp32s3 \
  write-flash -z 0x0 adafruit-circuitpython-adafruit_qtpy_esp32s3_nopsram-en_US-10.1.4.bin
```

Wrote 1,838,672 bytes in 17.3 seconds. Hash verified.

### Dev environment notes

- Host: Fedora Aurora (Universal Blue), immutable root, IBM ThinkPad
- Dev container: Debian via distrobox
- Serial device `/dev/ttyACM0` visible in container but permissions
  require `chmod 666` from host — `dialout` group does not exist on
  Aurora. Long-term fix: udev rule on host.
- `esptool` installed via `uv tool install esptool` on host
  (`~/.local/bin/esptool`)
- Flashing must be done from host terminal (container cannot chmod
  device files)
- CIRCUITPY drive mounts on host at `/run/media/amj/CIRCUITPY` —
  accessible from distrobox if path is bind-mounted or symlinked

## Serial Console Access

### 2026-03-10 — The `screen` Package vs. Atomic Fedora

Goal: connect to CircuitPython REPL via serial (`/dev/ttyACM0`).

Attempted to install `minicom` and `screen` on the host via
`rpm-ostree install` (Aurora wraps this as `dnf`). Rebooted.
Neither binary was present — unclear whether the install silently
failed or the deployment was replaced by an OS update.

Second attempt revealed `screen` cannot be layered: its RPM
expects a `screen` system group in `/etc/group`, but rpm-ostree
builds packages against the OSTree image's group file, not the
live system. Running `groupadd -r screen` on the live host does
not help — the build environment doesn't see it.

**Resolution:** Installed `minicom` only (layers cleanly).
`screen` is not available on atomic Fedora without a custom
sysusers.d override or a container workaround.

Alternatives for serial console:
- `minicom` (layered via rpm-ostree) ✓
- `picocom` (lightweight, may layer cleanly — untested)
- `cat /dev/ttyACM0` + `stty` (no install needed, janky)

After `rpm-ostree install minicom`, reboot required to activate.

## CircuitPython Library Install — Gotchas

### .mpy incompatibility (2026-03-10)

`circup install` defaults to precompiled `.mpy` bundles. CircuitPython
10.x uses a new .mpy format, and the bundled `.mpy` files may not match.

Symptom: `ValueError: incompatible .mpy file` on import at boot.

**Fix:** Always install with `--py` flag to get plain Python source:
```bash
circup --path /run/media/amj/CIRCUITPY install --py adafruit_ntp adafruit_httpserver
```

### Filesystem is read-only from REPL while USB is connected

CircuitPython locks the filesystem for USB mass storage. You cannot
delete or modify files from the REPL while the host has it mounted.

- `storage.remount("/", readonly=False)` → "Cannot remount path when
  visible via USB"
- To recover from bad library installs: run `storage.erase_filesystem()`
  from the REPL. This wipes the user filesystem only (firmware stays),
  board reboots with a fresh empty CIRCUITPY.
- After erase, the drive may re-enumerate as a different `/dev/sdX`.
  Always re-check `lsblk -f` before mounting.

### Distrobox cannot mount block devices

All mount/unmount and file copy to CIRCUITPY must happen from the
**host terminal**, not distrobox. The container can see host mounts
via `/run/host/run/media/` but this path is unreliable after remounts.

### Deploy checklist (host terminal)

```bash
CP=/run/media/amj/CIRCUITPY
SRC=/var/home/amj/mqqn/understory/software

sudo mount -o rw,fmask=0000,dmask=0000 /dev/sdX1 "$CP"
cp "$SRC/code.py" "$CP/"
cp "$SRC/schedule.json" "$CP/"
mkdir -p "$CP/static"
cp "$SRC/static/index.html" "$CP/static/"
cp "$SRC/settings.toml" "$CP/"   # create from settings.toml.example; DO NOT commit
circup --path "$CP" install --py adafruit_ntp adafruit_httpserver
```

## Safety

- Always disconnect the grow light power supply before wiring
- Double-check diode orientation before powering on
- The MOSFET tab is connected to drain — don't let it short to ground
- If the light flickers at boot, check that R1 is connected and has
  good contact on the breadboard

"""
boot.py — runs before code.py on every boot.

Filesystem access mode:
  Normal boot:  code can write, USB is read-only
  Dev mode:     USB can write, code is read-only

Dev mode: connect pin A1 to GND at boot (e.g., jumper wire).
"""

import board
import digitalio
import storage

dev_pin = digitalio.DigitalInOut(board.A1)
dev_pin.direction = digitalio.Direction.INPUT
dev_pin.pull = digitalio.Pull.UP

if not dev_pin.value:
    # A1 pulled to GND — dev mode, USB writable (default behavior)
    print("boot.py: DEV MODE — USB writable, code read-only")
else:
    # Normal boot — code writable, USB read-only
    storage.remount("/", readonly=False)
    print("boot.py: PRODUCTION — code writable, USB read-only")

dev_pin.deinit()

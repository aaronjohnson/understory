#!/bin/bash
# Flash CircuitPython onto QT Py ESP32-S3 (4MB Flash / 2MB PSRAM)
# Run from host terminal (not distrobox) — needs serial device access.
#
# Usage:
#   1. Put board in bootloader mode: hold BOOT, tap RESET, release BOOT
#   2. ./flash.sh

set -euo pipefail

FIRMWARE="adafruit-circuitpython-adafruit_qtpy_esp32s3_4mbflash_2mbpsram-en_US-10.1.4.bin"
URL="https://downloads.circuitpython.org/bin/adafruit_qtpy_esp32s3_4mbflash_2mbpsram/en_US/${FIRMWARE}"
PORT="/dev/ttyACM0"

cd "$(dirname "$0")"

# Download firmware if not already present
if [ ! -f "$FIRMWARE" ]; then
    echo "Downloading ${FIRMWARE}..."
    curl -LO "$URL"
else
    echo "Firmware already downloaded."
fi

# Fix serial device permissions
echo "Setting permissions on ${PORT}..."
sudo chmod 666 "$PORT"

# Flash
echo "Flashing..."
esptool --port "$PORT" --chip esp32s3 \
    write-flash -z 0x0 "$FIRMWARE"

echo ""
echo "Done. Board should reboot into CircuitPython."
echo "Look for CIRCUITPY drive in /run/media/$USER/"

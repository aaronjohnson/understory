#!/bin/bash
# Deploy understory to CIRCUITPY device.
# Run from host terminal (not distrobox) — needs mount access.
#
# Usage:
#   ./deploy.sh          # deploy all files
#   ./deploy.sh code     # deploy just code.py (quick iteration)

set -euo pipefail

CP="/run/media/amj/CIRCUITPY"
SRC="$(dirname "$0")/software"
DEV="/dev/sda1"

# Find the CIRCUITPY block device
for d in /dev/sda1 /dev/sdb1 /dev/sdc1; do
    if blkid "$d" 2>/dev/null | grep -q CIRCUITPY; then
        DEV="$d"
        break
    fi
done

# Mount if needed
if ! mountpoint -q "$CP" 2>/dev/null; then
    echo "Mounting $DEV at $CP..."
    sudo mkdir -p "$CP"
    sudo mount -o rw,fmask=0000,dmask=0000 "$DEV" "$CP"
fi

if [ "${1:-all}" = "code" ]; then
    echo "Deploying code.py only..."
    cp "$SRC/code.py" "$CP/"
else
    echo "Deploying all files..."
    cp "$SRC/code.py" "$CP/"
    cp "$SRC/schedule.json" "$CP/"
    mkdir -p "$CP/static"
    cp "$SRC/static/index.html" "$CP/static/"

    # Copy settings.toml if it exists (contains WiFi creds, not in git)
    if [ -f "$SRC/settings.toml" ]; then
        cp "$SRC/settings.toml" "$CP/"
    fi

    # Copy boot.py if it exists
    if [ -f "$SRC/boot.py" ]; then
        cp "$SRC/boot.py" "$CP/"
    fi
fi

sync
echo "Done. Board should auto-reload."

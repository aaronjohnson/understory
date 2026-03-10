"""
Herb Garden Light Controller
=============================
WiFi-enabled grow light scheduler.

Phase 1: Onboard LED + web UI + NTP schedule.
Phase 2: Swap onboard LED for MOSFET on pin A0.

CircuitPython 10.x on Adafruit QT Py ESP32-S3.
"""

import os
import time
import json
import board
import digitalio
import wifi
import socketpool
import mdns
import adafruit_ntp
from adafruit_httpserver import Server, Request, Response

# ── Configuration ──────────────────────────────────────────
TIMEZONE_OFFSET = -7
HOSTNAME = "herbgarden"
SCHEDULE_FILE = "/schedule.json"

# ── Hardware ───────────────────────────────────────────────
light = digitalio.DigitalInOut(board.A0)
light.direction = digitalio.Direction.OUTPUT
light.value = False


def load_schedule():
    """Load schedule from flash storage."""
    try:
        with open(SCHEDULE_FILE, "r") as f:
            data = json.load(f)
        # Migrate old single-period format
        if "on_hour" in data and "periods" not in data:
            data = migrate_schedule(data)
            save_schedule(data)
        return data
    except (OSError, ValueError) as e:
        print(f"Schedule load failed: {e}, using default")
        return default_schedule()


def migrate_schedule(old):
    """Convert single-period schedule to multi-period format."""
    return {
        "periods": [{
            "on_hour": old["on_hour"],
            "on_minute": old["on_minute"],
            "off_hour": old["off_hour"],
            "off_minute": old["off_minute"],
        }],
        "enabled": old.get("enabled", True),
    }


def save_schedule(schedule):
    """Persist schedule to flash storage."""
    try:
        with open(SCHEDULE_FILE, "w") as f:
            json.dump(schedule, f)
        print("Schedule saved")
    except OSError as e:
        print(f"Schedule save failed: {e}")


def default_schedule():
    return {
        "periods": [
            {"on_hour": 6, "on_minute": 0, "off_hour": 22, "off_minute": 0},
        ],
        "enabled": True,
        "quiet_start": 23,
        "quiet_end": 5,
    }


def in_quiet_hours(now, schedule):
    """Check if current time is within quiet hours."""
    qs = schedule.get("quiet_start", -1)
    qe = schedule.get("quiet_end", -1)
    if qs < 0 or qe < 0:
        return False
    hour = now.tm_hour
    if qs > qe:
        return hour >= qs or hour < qe
    else:
        return qs <= hour < qe


def should_be_on(now, schedule):
    """Check if light should be on based on any active period."""
    if not schedule.get("enabled", True):
        return False

    if in_quiet_hours(now, schedule):
        return False

    current_minutes = now.tm_hour * 60 + now.tm_min

    for p in schedule.get("periods", []):
        on_minutes = p["on_hour"] * 60 + p["on_minute"]
        off_minutes = p["off_hour"] * 60 + p["off_minute"]

        if on_minutes <= off_minutes:
            if on_minutes <= current_minutes < off_minutes:
                return True
        else:
            if current_minutes >= on_minutes or current_minutes < off_minutes:
                return True

    return False


def serve_index(request: Request):
    """Serve the scheduling web UI."""
    try:
        with open("/static/index.html", "r") as f:
            return Response(request, f.read(), content_type="text/html")
    except OSError:
        return Response(request, "<h1>Herb Garden</h1><p>UI not found</p>",
                        content_type="text/html")


def serve_status(request: Request):
    """Return current status as JSON."""
    status = {
        "light_on": light.value,
        "schedule": schedule,
    }
    return Response(request, json.dumps(status),
                    content_type="application/json")


def handle_toggle(request: Request):
    """Toggle light or set explicit state. POST /toggle, /toggle/on, /toggle/off."""
    global schedule
    path = request.path
    if path == "/toggle/on":
        light.value = True
    elif path == "/toggle/off":
        light.value = False
    else:
        light.value = not light.value
    state = "on" if light.value else "off"
    print(f"Manual toggle: {state}")
    return Response(request, '{"light_on":' + ('true' if light.value else 'false') + '}',
                    content_type="application/json")


def handle_schedule_update(request: Request):
    """Accept schedule update via POST."""
    global schedule
    try:
        new_schedule = json.loads(request.body)
        if "periods" not in new_schedule:
            return Response(request, '{"error":"missing periods"}',
                            content_type="application/json", status=400)
        for p in new_schedule["periods"]:
            for key in ("on_hour", "on_minute", "off_hour", "off_minute"):
                if key not in p:
                    return Response(request, '{"error":"missing field in period"}',
                                    content_type="application/json", status=400)
        new_schedule["enabled"] = new_schedule.get("enabled", True)
        schedule = new_schedule
        save_schedule(schedule)
        return Response(request, '{"ok":true}',
                        content_type="application/json")
    except (ValueError, KeyError) as e:
        return Response(request, f'{{"error":"{e}"}}',
                        content_type="application/json", status=400)


# ── Boot Sequence ──────────────────────────────────────────
print()
print("  understory")
print("  how does your garden grow?")
print()

print("  finding the network...", end=" ")
try:
    wifi.radio.connect(
        os.getenv("CIRCUITPY_WIFI_SSID"),
        os.getenv("CIRCUITPY_WIFI_PASSWORD"),
    )
    print(f"found it. {wifi.radio.ipv4_address}")
except Exception as e:
    print(f"lost. ({e})")

try:
    mdns_server = mdns.Server(wifi.radio)
    mdns_server.hostname = HOSTNAME
    mdns_server.advertise_service(
        service_type="_http",
        protocol="_tcp",
        port=80,
    )
    print(f"  announcing ourselves as {HOSTNAME}.local")
except Exception as e:
    print(f"  mDNS: couldn't advertise ({e})")

pool = socketpool.SocketPool(wifi.radio)
try:
    ntp = adafruit_ntp.NTP(pool, tz_offset=TIMEZONE_OFFSET)
    current_time = ntp.datetime
    print(f"  asking the internet what time it is... "
          f"{current_time.tm_hour:02d}:{current_time.tm_min:02d}. good.")
except Exception as e:
    print(f"  time sync failed. we'll guess. ({e})")
    ntp = None

schedule = load_schedule()
n = len(schedule.get("periods", []))
qs = schedule.get("quiet_start", -1)
qe = schedule.get("quiet_end", -1)
print(f"  schedule loaded. {n} period{'s' if n != 1 else ''}.")
for i, p in enumerate(schedule.get("periods", [])):
    print(f"    {p['on_hour']:02d}:{p['on_minute']:02d}"
          f" - {p['off_hour']:02d}:{p['off_minute']:02d}")
if qs >= 0 and qe >= 0:
    print(f"  quiet hours: {qs:02d}:00 - {qe:02d}:00. the herbs sleep.")
if not schedule.get("enabled", True):
    print("  schedule is paused. the light waits.")

server = Server(pool)
server.route("/")(serve_index)
server.route("/status")(serve_status)
server.route("/schedule", methods=["POST"])(handle_schedule_update)
server.route("/toggle", methods=["POST"])(handle_toggle)
server.route("/toggle/on", methods=["POST"])(handle_toggle)
server.route("/toggle/off", methods=["POST"])(handle_toggle)

try:
    server.start(str(wifi.radio.ipv4_address), port=80)
    print(f"  listening on http://{wifi.radio.ipv4_address}")
except Exception as e:
    print(f"  server couldn't start. ({e})")

print()
print("  the garden is open.")
print()

# ── Main Loop ──────────────────────────────────────────────
# Use local RTC after initial NTP sync — no network calls in the loop.
# Re-sync NTP every 6 hours to prevent drift.
import rtc
last_state = None
last_ntp_sync = time.monotonic()
NTP_RESYNC_INTERVAL = 6 * 3600

while True:
    try:
        server.poll()
    except Exception as e:
        print(f"Server poll error: {e}")

    try:
        now = time.localtime()
        new_state = should_be_on(now, schedule)
        light.value = new_state

        if new_state != last_state:
            state_str = "ON" if new_state else "OFF"
            print(f"  {now.tm_hour:02d}:{now.tm_min:02d} light {state_str}")
            last_state = new_state
    except Exception as e:
        print(f"  time error: {e}")

    # Periodic NTP re-sync
    if ntp and (time.monotonic() - last_ntp_sync) > NTP_RESYNC_INTERVAL:
        try:
            ntp.datetime  # triggers re-sync, updates RTC
            last_ntp_sync = time.monotonic()
        except Exception:
            pass  # silent — we'll try again next interval

    time.sleep(1)

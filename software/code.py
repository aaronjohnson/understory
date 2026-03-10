"""
Herb Garden Light Controller
=============================
WiFi-enabled grow light scheduler.

Phase 1: Onboard LED + web UI + NTP schedule.
Phase 2: Swap onboard LED for MOSFET on pin A0.

CircuitPython 9.x on Adafruit QT Py ESP32-S3.
"""

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
# WiFi credentials come from settings.toml:
#   CIRCUITPY_WIFI_SSID = "your-network"
#   CIRCUITPY_WIFI_PASSWORD = "your-password"
#
# Timezone offset (hours from UTC):
#   TIMEZONE_OFFSET = -8  (Pacific Standard)

TIMEZONE_OFFSET = -8
HOSTNAME = "herbgarden"
SCHEDULE_FILE = "/schedule.json"

# ── Hardware ───────────────────────────────────────────────
# Phase 1: use onboard NeoPixel or LED for testing
# Phase 2: switch to board.A0 for MOSFET gate
light = digitalio.DigitalInOut(board.A0)
light.direction = digitalio.Direction.OUTPUT
light.value = False


def load_schedule():
    """Load schedule from flash storage."""
    try:
        with open(SCHEDULE_FILE, "r") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"Schedule load failed: {e}, using default")
        return default_schedule()


def save_schedule(schedule):
    """Persist schedule to flash storage."""
    try:
        with open(SCHEDULE_FILE, "w") as f:
            json.dump(schedule, f)
        print("Schedule saved")
    except OSError as e:
        print(f"Schedule save failed: {e}")


def default_schedule():
    """Sensible default: 6AM-10PM daily, quiet hours 11PM-5AM."""
    return {
        "on_hour": 6,
        "on_minute": 0,
        "off_hour": 22,
        "off_minute": 0,
        "enabled": True,
    }


def should_be_on(now, schedule):
    """Determine if the light should be on right now.

    Args:
        now: time.struct_time from NTP
        schedule: dict with on_hour, on_minute, off_hour, off_minute, enabled

    Returns:
        bool: True if light should be on
    """
    if not schedule.get("enabled", True):
        return False

    current_minutes = now.tm_hour * 60 + now.tm_min
    on_minutes = schedule["on_hour"] * 60 + schedule["on_minute"]
    off_minutes = schedule["off_hour"] * 60 + schedule["off_minute"]

    if on_minutes <= off_minutes:
        # Normal case: on during the day (e.g., 6:00-22:00)
        return on_minutes <= current_minutes < off_minutes
    else:
        # Overnight case: on through midnight (e.g., 22:00-6:00)
        return current_minutes >= on_minutes or current_minutes < off_minutes


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


def handle_schedule_update(request: Request):
    """Accept schedule update via POST."""
    global schedule
    try:
        new_schedule = json.loads(request.body)
        # Validate required fields
        for key in ("on_hour", "on_minute", "off_hour", "off_minute"):
            if key not in new_schedule:
                return Response(request, '{"error":"missing field"}',
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
print("=" * 40)
print("Herb Garden Light Controller")
print("=" * 40)

# Connect to WiFi
print(f"Connecting to WiFi...")
try:
    wifi.radio.connect(
        os.getenv("CIRCUITPY_WIFI_SSID"),
        os.getenv("CIRCUITPY_WIFI_PASSWORD"),
    )
    print(f"Connected: {wifi.radio.ipv4_address}")
except Exception as e:
    print(f"WiFi failed: {e}")
    # Continue anyway — schedule still works if time was synced previously

# Set up mDNS (herbgarden.local)
try:
    mdns_server = mdns.Server(wifi.radio)
    mdns_server.hostname = HOSTNAME
    mdns_server.advertise_service(
        service_type="_http",
        protocol="_tcp",
        port=80,
    )
    print(f"mDNS: http://{HOSTNAME}.local")
except Exception as e:
    print(f"mDNS failed: {e}")

# Sync clock via NTP
pool = socketpool.SocketPool(wifi.radio)
try:
    ntp = adafruit_ntp.NTP(pool, tz_offset=TIMEZONE_OFFSET)
    current_time = ntp.datetime
    print(f"NTP synced: {current_time.tm_hour:02d}:{current_time.tm_min:02d}")
except Exception as e:
    print(f"NTP failed: {e}")
    ntp = None

# Load schedule
schedule = load_schedule()
print(f"Schedule: {schedule['on_hour']:02d}:{schedule['on_minute']:02d}"
      f" - {schedule['off_hour']:02d}:{schedule['off_minute']:02d}"
      f" ({'enabled' if schedule['enabled'] else 'disabled'})")

# Start web server
server = Server(pool)
server.route("/")(serve_index)
server.route("/status")(serve_status)
server.route("/schedule", methods=["POST"])(handle_schedule_update)

try:
    server.start(str(wifi.radio.ipv4_address))
    print(f"Server running on http://{wifi.radio.ipv4_address}")
except Exception as e:
    print(f"Server start failed: {e}")

print("Entering main loop")
print("=" * 40)

# ── Main Loop ──────────────────────────────────────────────
last_state = None

while True:
    try:
        server.poll()
    except Exception as e:
        print(f"Server poll error: {e}")

    if ntp:
        try:
            now = ntp.datetime
            new_state = should_be_on(now, schedule)
            light.value = new_state

            # Log state changes
            if new_state != last_state:
                state_str = "ON" if new_state else "OFF"
                print(f"{now.tm_hour:02d}:{now.tm_min:02d} Light {state_str}")
                last_state = new_state
        except Exception as e:
            print(f"Time/schedule error: {e}")

    time.sleep(1)

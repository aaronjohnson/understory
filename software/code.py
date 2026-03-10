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
import rtc
import adafruit_ntp
from adafruit_httpserver import Server, Request, Response

# ── Configuration ──────────────────────────────────────────
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", -7))
VERSION = "0.4.0"
HOSTNAME = "herbgarden"
SCHEDULE_FILE = "/schedule.json"
LOG_FILE = "/log.txt"
LOG_MAX_LINES = 200


def log(msg):
    """Print to serial and append to log file on flash."""
    print(msg)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(msg.strip() + "\n")
    except OSError:
        pass  # read-only filesystem (dev mode) — serial only


def trim_log():
    """Keep log file from growing forever."""
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        if len(lines) > LOG_MAX_LINES:
            with open(LOG_FILE, "w") as f:
                f.writelines(lines[-LOG_MAX_LINES:])
    except OSError:
        pass

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


def local_now():
    """Get local time. Uses NTP monotonic offset (no network call)."""
    if ntp:
        try:
            return ntp.datetime
        except Exception:
            pass
    # Fallback: offset from RTC (may be UTC if NTP never synced)
    utc = time.time()
    local_epoch = utc + TIMEZONE_OFFSET * 3600
    if local_epoch < 0:
        local_epoch = 0
    return time.localtime(local_epoch)


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


# ── Adaptive Clock ─────────────────────────────────────────
# Nagle-style NTP sync: starts frequent, backs off when drift is low,
# tightens when drift is high. Periodic probe prevents stale assumptions.

class AdaptiveClock:
    MIN_INTERVAL = 900       # 15 minutes
    MAX_INTERVAL = 86400     # 24 hours
    PROBE_AFTER = 10         # force a tight sync after N consecutive backoffs
    DEFAULT_EPSILON = 30     # seconds of tolerable drift

    HISTORY_FILE = "/clock_log.json"
    HISTORY_MAX = 50  # entries persisted to disk

    def __init__(self, ntp_client):
        self.ntp = ntp_client
        self.interval = 3600          # start at 1 hour
        self.last_sync = time.monotonic()
        self.last_drift = 0.0
        self.syncs = 0
        self.consecutive_stable = 0
        self.history = self._load_history()
        self.settled = False
        self.settled_at_sync = -1

    def _load_history(self):
        try:
            with open(self.HISTORY_FILE, "r") as f:
                data = json.load(f)
            print(f"  clock: resumed with {len(data)} sync records")
            return data
        except (OSError, ValueError):
            return []

    def _save_history(self):
        try:
            with open(self.HISTORY_FILE, "w") as f:
                json.dump(self.history[-self.HISTORY_MAX:], f)
        except OSError:
            pass

    @property
    def epsilon(self):
        return schedule.get("ntp_epsilon", self.DEFAULT_EPSILON)

    def maybe_sync(self):
        if not self.ntp:
            return
        elapsed = time.monotonic() - self.last_sync
        if elapsed < self.interval:
            return
        self._do_sync()

    def _do_sync(self):
        try:
            # Snapshot current time before sync (monotonic-based, no network)
            before_ns = self.ntp.utc_ns

            # Force a fresh NTP query by resetting the cache
            self.ntp.next_sync = 0
            _ = self.ntp.datetime  # triggers network call

            # Snapshot after sync
            after_ns = self.ntp.utc_ns

            # Drift = how much the clock jumped (minus ~network latency)
            # If clock was perfect, jump ≈ 0 (just round-trip time ~0.1-0.5s)
            # If clock had drifted, the jump is larger
            drift_secs = abs(after_ns - before_ns) / 1_000_000_000
            # Subtract a rough network round-trip estimate
            drift_secs = max(0, drift_secs - 0.5)
            self.last_drift = drift_secs

            self.syncs += 1
            self.last_sync = time.monotonic()
            # Keep cache large so ntp.datetime reads don't trigger network calls
            self.ntp.next_sync = time.monotonic_ns() + 999999 * 1_000_000_000

            # Adaptive interval
            old_interval = self.interval
            if drift_secs < self.epsilon:
                self.consecutive_stable += 1
                self.interval = min(self.interval * 2, self.MAX_INTERVAL)
                direction = "stable"
            else:
                self.consecutive_stable = 0
                self.interval = max(self.interval // 2, self.MIN_INTERVAL)
                self.settled = False
                self.settled_at_sync = -1
                direction = "correcting"

            # Detect settled state
            if not self.settled and self.interval >= self.MAX_INTERVAL // 2:
                self.settled = True
                self.settled_at_sync = self.syncs

            # Periodic probe: after many stable syncs, force one tight
            # sync to verify assumptions still hold
            if self.consecutive_stable >= self.PROBE_AFTER:
                self.interval = self.MIN_INTERVAL
                self.consecutive_stable = 0
                direction = "probing"

            # Log
            interval_h = self.interval / 3600
            if interval_h >= 1:
                interval_str = f"{interval_h:.1f}h"
            else:
                interval_str = f"{self.interval // 60}m"

            entry = {
                "sync": self.syncs,
                "drift": round(drift_secs, 2),
                "interval": self.interval,
                "direction": direction,
                "uptime": int(time.monotonic()),
            }
            self.history.append(entry)
            if len(self.history) > self.HISTORY_MAX:
                self.history.pop(0)
            self._save_history()

            log(f"  ntp sync #{self.syncs}: ~{drift_secs:.1f}s drift, "
                f"next in {interval_str} ({direction})")

        except Exception as e:
            print(f"  ntp sync failed: {e}")

    def status(self):
        """Return clock status for the API/UI."""
        interval_h = self.interval / 3600
        if interval_h >= 1:
            interval_str = f"{interval_h:.1f}h"
        else:
            interval_str = f"{self.interval // 60}m"
        return {
            "syncs": self.syncs,
            "interval": self.interval,
            "interval_str": interval_str,
            "last_drift": round(self.last_drift, 2),
            "settled": self.settled,
            "settled_at_sync": self.settled_at_sync,
            "epsilon": self.epsilon,
            "history": self.history,
        }


try:
    with open("/static/index.html", "r") as f:
        _INDEX_HTML = f.read()
except OSError:
    _INDEX_HTML = "<h1>Herb Garden</h1><p>UI not found</p>"


def serve_index(request: Request):
    """Serve the scheduling web UI (cached in RAM)."""
    return Response(request, _INDEX_HTML, content_type="text/html")


def serve_status(request: Request):
    """Return current status as JSON."""
    status = {
        "version": VERSION,
        "light_on": light.value,
        "schedule": schedule,
        "clock": clock.status(),
    }
    return Response(request, json.dumps(status),
                    content_type="application/json")


def handle_toggle(request: Request):
    """Toggle light or set explicit state. POST /toggle, /toggle/on, /toggle/off."""
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
trim_log()
print()
log(f"  understory v{VERSION} boot")
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
ntp = None
try:
    ntp = adafruit_ntp.NTP(pool, tz_offset=TIMEZONE_OFFSET,
                           cache_seconds=999999)
    now = ntp.datetime
    print(f"  asking the internet what time it is... "
          f"{now.tm_hour:02d}:{now.tm_min:02d}. good.")
except Exception as e:
    print(f"  time sync failed. we'll guess. ({e})")
    ntp = None

clock = AdaptiveClock(ntp)

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
last_state = None

while True:
    try:
        server.poll()
    except Exception as e:
        print(f"Server poll error: {e}")

    try:
        now = local_now()
        # Skip schedule evaluation if clock hasn't synced (year 2020 = no NTP)
        if now.tm_year <= 2020:
            time.sleep(1)
            continue
        new_state = should_be_on(now, schedule)
        light.value = new_state

        if new_state != last_state:
            state_str = "ON" if new_state else "OFF"
            log(f"  {now.tm_hour:02d}:{now.tm_min:02d} light {state_str}")
            last_state = new_state
    except Exception as e:
        print(f"  time error: {e}")

    clock.maybe_sync()
    time.sleep(1)

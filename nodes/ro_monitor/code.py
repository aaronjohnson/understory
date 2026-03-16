"""
RO Water Quality Monitor
=========================
Reverse osmosis membrane health monitor.

Reads TDS (total dissolved solids) pre- and post-membrane,
water flow rate, and temperature for TDS compensation.
Derives membrane rejection rate and tracks lifetime volume.

CircuitPython 10.x on Adafruit QT Py ESP32-S3.
"""

import os
import time
import json
import board
import analogio
import countio
import digitalio
import wifi
import socketpool
import mdns
import microcontroller
import adafruit_ntp
from adafruit_httpserver import Server, Request, Response

try:
    from adafruit_onewire.bus import OneWireBus
    import adafruit_ds18x20
    HAS_TEMP_SENSOR = True
except ImportError:
    HAS_TEMP_SENSOR = False

# ── Configuration ──────────────────────────────────────────
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", -8))
VERSION = "0.1.0"
HOSTNAME = "romonitor"
THRESHOLDS_FILE = "/thresholds.json"
VOLUME_FILE = "/volume.json"
LOG_FILE = "/log.txt"
LOG_MAX_LINES = 200

# Sensor calibration
TDS_SAMPLES = 30           # analog reads to average per measurement
TDS_SAMPLE_DELAY = 0.01   # seconds between ADC reads
FLOW_PULSES_PER_LITER = 450
FLOW_SAMPLE_WINDOW = 1.0  # seconds
VOLUME_WRITE_EVERY = 10   # liters between flash writes
DEFAULT_TEMP_C = 25.0     # fallback if no temp sensor

# Pin assignments
PIN_TDS_PRE = board.A0
PIN_TDS_POST = board.A1
PIN_TEMP = board.TX       # DS18B20 1-Wire data
PIN_FLOW = board.RX       # YF-S201 pulse input


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


# ── Thresholds ─────────────────────────────────────────────

def load_thresholds():
    """Load alert thresholds from flash storage."""
    try:
        with open(THRESHOLDS_FILE, "r") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"Thresholds load failed: {e}, using defaults")
        return default_thresholds()


def default_thresholds():
    """Default alert thresholds."""
    return {
        "tds_alert_ppm": 50,
        "tds_warn_ppm": 20,
        "flow_min_lpm": 0.1,
        "membrane_life_liters": 2000,
    }


def save_thresholds(thresholds):
    """Persist thresholds to flash storage."""
    try:
        with open(THRESHOLDS_FILE, "w") as f:
            json.dump(thresholds, f)
        print("Thresholds saved")
    except OSError as e:
        print(f"Thresholds save failed: {e}")


# ── Volume Persistence ─────────────────────────────────────

def load_volume():
    """Load lifetime volume counter from flash."""
    try:
        with open(VOLUME_FILE, "r") as f:
            data = json.load(f)
        return data.get("liters_lifetime", 0.0), data.get("liters_today", 0.0)
    except (OSError, ValueError):
        return 0.0, 0.0


def save_volume(liters_lifetime, liters_today):
    """Persist volume counter to flash. Throttled to reduce wear."""
    try:
        with open(VOLUME_FILE, "w") as f:
            json.dump({
                "liters_lifetime": round(liters_lifetime, 2),
                "liters_today": round(liters_today, 2),
            }, f)
    except OSError:
        pass


# ── TDS Sensor ─────────────────────────────────────────────

def read_tds_voltage(adc_pin):
    """Read averaged analog voltage from TDS sensor."""
    total = 0
    for _ in range(TDS_SAMPLES):
        total += adc_pin.value
        time.sleep(TDS_SAMPLE_DELAY)
    avg = total / TDS_SAMPLES
    # QT Py ESP32-S3: 16-bit ADC, 3.3V reference
    voltage = (avg / 65535) * 3.3
    return voltage


def voltage_to_tds(voltage, temp_c=25.0):
    """Convert TDS sensor voltage to ppm with temperature compensation.

    Uses the DFRobot Gravity TDS sensor conversion formula.
    Temperature coefficient: ~2% per degree C from 25C reference.
    """
    temp_coeff = 1.0 + 0.02 * (temp_c - 25.0)
    compensated_v = voltage / temp_coeff
    # DFRobot polynomial conversion
    tds = (133.42 * compensated_v ** 3
           - 255.86 * compensated_v ** 2
           + 857.39 * compensated_v) * 0.5
    return max(0.0, tds)


def rejection_rate(tds_pre, tds_post):
    """Calculate membrane rejection rate as percentage.

    Returns 0.0 if pre-membrane TDS is zero (avoids division by zero).
    """
    if tds_pre <= 0:
        return 0.0
    return (1.0 - tds_post / tds_pre) * 100.0


# ── Temperature Sensor ─────────────────────────────────────

def init_temp_sensor():
    """Initialize DS18B20 temperature sensor. Returns sensor or None."""
    if not HAS_TEMP_SENSOR:
        print("  temp sensor libraries not installed")
        return None
    try:
        ow_bus = OneWireBus(PIN_TEMP)
        devices = ow_bus.scan()
        if not devices:
            print("  no 1-Wire devices found")
            return None
        sensor = adafruit_ds18x20.DS18X20(ow_bus, devices[0])
        print(f"  DS18B20 found: {sensor.temperature:.1f}C")
        return sensor
    except Exception as e:
        print(f"  temp sensor init failed: {e}")
        return None


def read_temp(sensor):
    """Read temperature in Celsius. Returns default if sensor unavailable."""
    if sensor is None:
        return DEFAULT_TEMP_C
    try:
        return sensor.temperature
    except Exception:
        return DEFAULT_TEMP_C


# ── Flow Sensor ────────────────────────────────────────────

def init_flow_sensor():
    """Initialize flow sensor pulse counter on RX pin."""
    try:
        counter = countio.Counter(PIN_FLOW, edge=countio.Edge.RISE)
        print("  flow sensor initialized")
        return counter
    except Exception as e:
        print(f"  flow sensor init failed: {e}")
        return None


def read_flow_rate(counter, elapsed_seconds):
    """Read flow rate in liters per minute from pulse counter.

    Reads and resets the counter. elapsed_seconds is the time since
    the counter was last read.
    """
    if counter is None:
        return 0.0, 0
    pulses = counter.count
    counter.reset()
    if elapsed_seconds <= 0:
        return 0.0, pulses
    liters = pulses / FLOW_PULSES_PER_LITER
    lpm = (liters / elapsed_seconds) * 60.0
    return lpm, pulses


# ── Alert Logic ────────────────────────────────────────────

def evaluate_alerts(tds_post, flow_lpm, rejection_pct, thresholds):
    """Evaluate sensor readings against thresholds.

    Returns a dict of alert states.
    """
    alerts = {
        "tds_alert": tds_post > thresholds.get("tds_alert_ppm", 50),
        "tds_warn": tds_post > thresholds.get("tds_warn_ppm", 20),
        "flow_low": False,
        "rejection_low": rejection_pct < 80.0 if rejection_pct > 0 else False,
    }
    return alerts


def membrane_life_remaining(liters_lifetime, rejection_pct, thresholds):
    """Estimate remaining membrane life as a percentage.

    Based on volume used and rejection rate degradation.
    Returns a value 0-100.
    """
    max_liters = thresholds.get("membrane_life_liters", 2000)
    if max_liters <= 0:
        return 100.0
    volume_pct = max(0.0, 100.0 - (liters_lifetime / max_liters) * 100.0)
    # Penalize if rejection rate is dropping
    if rejection_pct > 0 and rejection_pct < 85:
        penalty = (85 - rejection_pct) * 2  # 2% penalty per % below 85
        volume_pct = max(0.0, volume_pct - penalty)
    return round(volume_pct, 1)


# ── Web Server ─────────────────────────────────────────────

try:
    with open("/static/index.html", "r") as f:
        _INDEX_HTML = f.read()
except OSError:
    _INDEX_HTML = "<h1>RO Monitor</h1><p>UI not found</p>"


# Global state (updated in main loop)
readings = {
    "tds_pre": 0.0,
    "tds_post": 0.0,
    "temp_c": DEFAULT_TEMP_C,
    "flow_lpm": 0.0,
    "rejection_pct": 0.0,
    "liters_today": 0.0,
    "liters_lifetime": 0.0,
    "membrane_life_pct": 100.0,
    "alerts": {},
    "last_update": 0,
}


def serve_index(request: Request):
    """Serve the monitoring web UI (cached in RAM)."""
    return Response(request, _INDEX_HTML, content_type="text/html")


def serve_status(request: Request):
    """Return current status as JSON."""
    status = {
        "version": VERSION,
        "readings": readings,
        "thresholds": thresholds,
    }
    return Response(request, json.dumps(status),
                    content_type="application/json")


def handle_thresholds_update(request: Request):
    """Accept threshold update via POST."""
    global thresholds
    try:
        new_thresholds = json.loads(request.body)
        for key in ("tds_alert_ppm", "tds_warn_ppm"):
            if key in new_thresholds:
                new_thresholds[key] = int(new_thresholds[key])
        thresholds.update(new_thresholds)
        save_thresholds(thresholds)
        return Response(request, '{"ok":true}',
                        content_type="application/json")
    except (ValueError, KeyError) as e:
        return Response(request, f'{{"error":"{e}"}}',
                        content_type="application/json", status=400)


def handle_reset_daily(request: Request):
    """Reset daily volume counter."""
    readings["liters_today"] = 0.0
    save_volume(readings["liters_lifetime"], 0.0)
    return Response(request, '{"ok":true}',
                    content_type="application/json")


# ── Boot Sequence ──────────────────────────────────────────
trim_log()
print()
log(f"  understory ro_monitor v{VERSION} boot")
print("  watching the water")
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

# Initialize sensors
print("  initializing sensors...")
tds_pre_adc = analogio.AnalogIn(PIN_TDS_PRE)
tds_post_adc = analogio.AnalogIn(PIN_TDS_POST)
print(f"  TDS sensors on A0 (pre) and A1 (post)")

temp_sensor = init_temp_sensor()
flow_counter = init_flow_sensor()

thresholds = load_thresholds()
print(f"  thresholds: alert={thresholds['tds_alert_ppm']}ppm, "
      f"warn={thresholds['tds_warn_ppm']}ppm")

liters_lifetime, liters_today = load_volume()
readings["liters_lifetime"] = liters_lifetime
readings["liters_today"] = liters_today
print(f"  volume: {liters_lifetime:.1f}L lifetime, {liters_today:.1f}L today")

server = Server(pool)
server.route("/")(serve_index)
server.route("/status")(serve_status)
server.route("/thresholds", methods=["POST"])(handle_thresholds_update)
server.route("/reset-daily", methods=["POST"])(handle_reset_daily)

try:
    server.start(str(wifi.radio.ipv4_address), port=80)
    print(f"  listening on http://{wifi.radio.ipv4_address}")
except Exception as e:
    print(f"  server couldn't start. ({e})")

print()
print("  the water is watched.")
print()

# ── Main Loop ──────────────────────────────────────────────
SENSOR_INTERVAL = 2.0  # seconds between sensor reads
last_sensor_read = time.monotonic()
last_volume_write = liters_lifetime
last_day = -1

if flow_counter:
    flow_counter.reset()

while True:
    try:
        server.poll()
    except Exception as e:
        print(f"Server poll error: {e}")

    now_mono = time.monotonic()
    elapsed = now_mono - last_sensor_read

    if elapsed >= SENSOR_INTERVAL:
        last_sensor_read = now_mono

        # Temperature (read first for TDS compensation)
        temp_c = read_temp(temp_sensor)

        # TDS readings
        v_pre = read_tds_voltage(tds_pre_adc)
        v_post = read_tds_voltage(tds_post_adc)
        tds_pre = voltage_to_tds(v_pre, temp_c)
        tds_post = voltage_to_tds(v_post, temp_c)
        rej_pct = rejection_rate(tds_pre, tds_post)

        # Flow rate
        flow_lpm, pulses = read_flow_rate(flow_counter, elapsed)
        liters_this_read = pulses / FLOW_PULSES_PER_LITER

        # Accumulate volume
        liters_today += liters_this_read
        liters_lifetime += liters_this_read

        # Alerts
        alerts = evaluate_alerts(tds_post, flow_lpm, rej_pct, thresholds)
        membrane_pct = membrane_life_remaining(
            liters_lifetime, rej_pct, thresholds)

        # Update global state
        readings["tds_pre"] = round(tds_pre, 1)
        readings["tds_post"] = round(tds_post, 1)
        readings["temp_c"] = round(temp_c, 1)
        readings["flow_lpm"] = round(flow_lpm, 2)
        readings["rejection_pct"] = round(rej_pct, 1)
        readings["liters_today"] = round(liters_today, 2)
        readings["liters_lifetime"] = round(liters_lifetime, 2)
        readings["membrane_life_pct"] = membrane_pct
        readings["alerts"] = alerts
        readings["last_update"] = now_mono

        # Persist volume periodically
        if liters_lifetime - last_volume_write >= VOLUME_WRITE_EVERY:
            save_volume(liters_lifetime, liters_today)
            last_volume_write = liters_lifetime

        # Daily reset check (if NTP available)
        if ntp:
            try:
                now_time = ntp.datetime
                today = now_time.tm_yday
                if last_day >= 0 and today != last_day:
                    log(f"  new day — resetting daily counter "
                        f"({liters_today:.1f}L)")
                    liters_today = 0.0
                    save_volume(liters_lifetime, liters_today)
                last_day = today
            except Exception:
                pass

        # Log alerts
        if alerts.get("tds_alert"):
            log(f"  ALERT: post-TDS {tds_post:.0f}ppm > "
                f"{thresholds['tds_alert_ppm']}ppm threshold")

    time.sleep(0.1)

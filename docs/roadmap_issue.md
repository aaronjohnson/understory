# Roadmap: sensor network expansion, coordinator, automated watering

**Labels:** enhancement

---

## Summary

Design notes from the ro_monitor build session. Captures the next
arcs for understory beyond grow light scheduling and water quality
monitoring.

## Single board vs. multi-node

The current plan uses one QT Py ESP32-S3 per function (herbgarden,
ro_monitor). If two nodes end up physically co-located, consolidating
onto one board saves cost and complexity. If they're in different
locations (counter vs. under sink), separate boards with the network
as the bus is cleaner. Decide per deployment.

## Coordinator layer

The QT Py nodes are leaf devices — read sensors, serve a local web
UI, expose a JSON API. Once orchestration is needed (watering
schedules that respond to soil moisture, fertilizer dosing, task
management, unified dashboard), a coordinator is the right pattern.

Options:
- **Elixir/Nerves on Raspberry Pi** — OTP supervisors for fault
  tolerance, GenServer per node, Phoenix LiveView for unified UI,
  native BEAM clustering if a second Pi is added later
- **Elixir on Mac mini** — same stack, runs alongside the existing
  SigNoz/OTel infrastructure
- **Rust** — where latency or resource constraints matter, though
  CircuitPython is a good intermediate environment for sensor nodes

## Firmware updates: poll vs. push

- **Poll** is simpler for CircuitPython devices. The ESP32 checks a
  known HTTP endpoint (local server on Pi/Mac mini, or GitHub raw
  URL) on a timer. OTA for CircuitPython = replacing files on the
  filesystem, not a binary flash
- **Push** makes more sense from a BEAM coordinator — maintain
  persistent connections or use MQTT as a message bus
- Hybrid: nodes poll a version endpoint, coordinator pushes via
  MQTT when an update is available

## Soil moisture + automated watering

Reuses existing patterns in the codebase:
- Capacitive soil moisture sensor → ADC pin (same as TDS sensors)
- Soil temperature → DS18B20 (same 1-Wire pattern as ro_monitor)
- Solenoid water valve → MOSFET on GPIO (same circuit as grow light)
- Watering schedule logic → same time-based approach as light schedule

This is the highest-value next firmware step — it's a small delta
from what's already built.

## Water quality experiments

Manual observation work, not firmware, but the ro_monitor provides
the measurement infrastructure:
- Filtered RO water + fertilizer vs. unfiltered tap + fertilizer
- Unfiltered water left standing to off-gas chlorine vs. fresh tap
- Track plant growth outcomes against water quality data over time

Could eventually feed into the coordinator as experiment tracking.

## Suggested sequence

1. Soil moisture + temperature sensors on herb garden node
2. Automated watering (solenoid valve, MOSFET, schedule)
3. Coordinator on Pi or Mac mini (Elixir/Phoenix LiveView)
4. Unified dashboard — all nodes, all sensors, one UI
5. MQTT or direct polling for firmware updates
6. OTLP metrics export to OTel Collector (stretch, existing infra)
7. Water quality grow experiments (manual + data logging)

## Philosophy

One step at a time. Only where it is fun. Automate the boring parts,
keep the gardening parts human.

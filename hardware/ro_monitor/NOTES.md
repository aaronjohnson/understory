# Hardware Notes — RO Monitor

## Sensors

| Component | Model | Interface | Notes |
|-----------|-------|-----------|-------|
| TDS sensor (×2) | DFRobot Gravity TDS | Analog voltage | 3.3V safe, one pre-membrane, one post-membrane |
| Flow sensor | YF-S201 | Hall effect pulse | ~450 pulses/liter, 5V tolerant |
| Temp sensor | DS18B20 | 1-Wire digital | For TDS temperature compensation |

## Pin Assignments (QT Py ESP32-S3)

| Pin | Use | Notes |
|-----|-----|-------|
| A0 | TDS sensor pre-membrane | Analog input |
| A1 | TDS sensor post-membrane | Analog input |
| A2 | Dev mode jumper (boot.py) | Pull-up, jumper to GND for dev mode |
| TX | DS18B20 data (1-Wire) | 4.7kΩ pull-up to 3.3V |
| RX | YF-S201 flow pulse input | Digital interrupt via countio |

## Wiring

### TDS Sensors (DFRobot Gravity)

Each TDS sensor has 3 wires:
- **Red** → 3.3V
- **Black** → GND
- **Yellow/Blue** (signal) → ADC pin (A0 for pre, A1 for post)

Place probe electrodes:
- Pre-membrane: in the feed water line (before RO membrane)
- Post-membrane: in the permeate water line (after RO membrane)

### DS18B20 Temperature Sensor

```
         ┌──────┐
  GND ───┤1     │
  DATA ──┤2  DS18B20
  3.3V ──┤3     │
         └──────┘

DATA pin → TX on QT Py
4.7kΩ pull-up resistor between DATA and 3.3V
```

Place the temperature probe in the feed water line near the
pre-membrane TDS sensor, since TDS readings are temperature-dependent.

### YF-S201 Flow Sensor

```
  Red wire   → 5V (or 3.3V — sensor works at 3.3-5V)
  Black wire → GND
  Yellow wire → RX on QT Py (pulse signal)
```

Install in-line on the permeate (output) water line to measure
filtered water production.

**Note:** The YF-S201 pulse output is open-collector and safe for
3.3V logic. No level shifter needed.

## Power

The QT Py ESP32-S3 can be powered via USB-C. For permanent
installation, a USB phone charger under the sink works well.

## Enclosure

Use a splash-rated enclosure (IP54 or better). The area under a
sink can get damp. Keep the QT Py and wiring connections dry.
Route sensor cables through cable glands.

## Calibration

### TDS Sensors

The DFRobot Gravity sensors ship factory-calibrated. For better
accuracy, calibrate with a known TDS reference solution:

1. Dip probe in reference solution (e.g., 342 ppm NaCl)
2. Read the voltage from the serial console
3. Adjust the polynomial coefficients in code.py if needed

### Flow Sensor

The YF-S201 nominal calibration is ~450 pulses per liter.
To verify:
1. Measure a known volume (e.g., 1L bottle)
2. Count pulses reported in serial output
3. Adjust FLOW_PULSES_PER_LITER in code.py

## Flash Log

(Record firmware flash details here after first deployment.)

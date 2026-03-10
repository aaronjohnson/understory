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

## Safety

- Always disconnect the grow light power supply before wiring
- Double-check diode orientation before powering on
- The MOSFET tab is connected to drain — don't let it short to ground
- If the light flickers at boot, check that R1 is connected and has
  good contact on the breadboard

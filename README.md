# Herb Garden Light Controller

WiFi-enabled grow light scheduler using an Adafruit QT Py ESP32-S3 and
a low-side N-channel MOSFET switch. CircuitPython firmware, no cloud,
no app — just a tiny web server on a chip the size of a postage stamp.

Connect to the local network and open `http://herbgarden.local` on your
phone to set the schedule.

## How It Works

A CircuitPython script on the ESP32 connects to WiFi, syncs the clock
via NTP, and runs a scheduling loop. When the schedule says ON, pin A0
goes HIGH (3.3V), which opens the gate of an STP55NF06L N-channel
MOSFET. Current flows through the grow light, through the MOSFET
drain-to-source, to ground. Light on. Schedule says OFF, A0 goes LOW,
MOSFET closes, light off.

The boundary between software and electricity is pin A0.
`light.value = True` becomes 3.3 volts on a wire.

## Bill of Materials

| Ref | Component             | DigiKey #        | Qty | Price  |
|-----|-----------------------|------------------|-----|--------|
| U1  | QT Py ESP32-S3        | 1528-5700-ND     | 1   | $12.50 |
| Q1  | STP55NF06L MOSFET     | 497-6742-5-ND    | 2   | $2.07  |
| D1  | 1N4007 Diode          | 1N4007DICT-ND    | 1   | $0.10  |
| R1  | 10kΩ 1/4W Resistor    | CF14JT10K0CT-ND  | 5   | $0.10  |
| --  | Jumper wire kit       | Global Spec.     | 1   | $5.60  |
| --  | Breadboard            | (search)         | 1   | ~$4    |

Estimated total: ~$28

## Build Phases

1. **Prove it works** (1 afternoon) — Flash CircuitPython. Connect WiFi.
   Sync time. Toggle onboard LED on schedule. Web UI on phone.
   No MOSFET yet.

2. **Real load** (1 evening) — Wire MOSFET on breadboard. Connect to
   grow light's DC ground. Control actual light from web UI.

3. **Install** (weekend) — Mount under cabinet. Solder permanent
   connections. Set schedule. Forget about it.

4. **Show off** (optional) — Blog post. MQTT for Home Assistant.
   Soil moisture sensor. Go wild.

## Repository Structure

```
understory/
├── README.md
├── CHANGELOG.md
├── LICENSE
├── docs/
│   ├── understory.tex    LaTeX source (schematic + docs)
│   └── (compile: cd docs && xelatex understory.tex)
├── hardware/
│   └── NOTES.md                      wiring notes, voltage checks
└── software/
    ├── code.py                       main firmware
    ├── settings.toml.example         WiFi config template
    ├── schedule.json                 default schedule
    ├── lib/                          CircuitPython libraries
    └── static/
        └── index.html                web UI
```

## Before You Start

Open the grow light base and identify the DC voltage: 12V or 24V.
This determines your power supply requirements.

## Building the Documentation

The 2-page schematic handout is built from LaTeX source. Requires
TeX Live with XeLaTeX and the `circuitikz` package:

```bash
cd docs
xelatex understory.tex
xelatex understory.tex   # second pass for refs
```

The PDF is intentionally not tracked in git (build artifact).

## License

MIT

## Acknowledgments

Schematic and documentation developed collaboratively with Claude
(Anthropic). Hardware design follows Adafruit's CircuitPython
ecosystem. Basil remains indifferent to all of this.

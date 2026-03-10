# Changelog

All notable changes to this project will be documented in this file.
Format inspired by the Dwarf Fortress changelog tradition.

## [0.1.0] - 2026-02-20

### The Planting

- Named the project `understory` — the shaded layer beneath the canopy, where light is managed
- Conceived entire project around a single MOSFET and a schedule
- Selected Adafruit QT Py ESP32-S3 as the brain (4MB flash, WiFi, USB-C, fits in a thimble)
- Selected STP55NF06L N-channel MOSFET as the muscle (60V/55A for a grow light is like hiring a bodyguard for a hamster)
- Added R1 pull-down resistor because the ESP32 has opinions about pin state during boot
- Added D1 flyback diode because inductors are spiteful when you cut their current
- Placed DigiKey order. Included spares because breadboards eat components
- Produced 2-page LaTeX handout with CircuiTikZ schematic
- Iterated schematic through 7 revisions to find the right balance between "readable" and "not a ransom note"
- Discovered that CircuiTikZ label placement is its own field of applied mathematics
- Established digital/analog domain boundary as a first-class concept in the documentation
- The basil is still alive and still does not care
- Created git repository with branch `taproot`

### Known Issues

- Have not yet identified DC voltage inside grow light (12V or 24V)
- Web UI does not exist yet
- The ESP32 is still in its anti-static bag
- Schedule logic exists only in prose

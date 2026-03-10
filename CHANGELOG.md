# Changelog

All notable changes to this project will be documented in this file.
Format inspired by the Dwarf Fortress changelog tradition.

## [0.3.0] - 2026-03-10

### The Tending

- The grow light now has a phone-friendly control panel. You can reach it
  from any device on the WiFi by visiting `http://herbgarden.local`
- Redesigned the interface to look like it belongs in a garden shed,
  not a stock trading app
- You can now set multiple light periods per day — e.g., morning burst
  plus evening session, because herbs have complex needs and simple ones
  at the same time
- Tap the glowing sun icon to flip the light on or off manually,
  for those 11pm moments when you just need to check on the basil
- You can add a button to your Android home screen that toggles
  the light with one tap. Ask Aaron how
- The schedule now actually remembers your changes after a reboot.
  Previously it forgot everything, like a goldfish with a grow light
- Created a one-command deploy script so Aaron stops having to type
  six commands every time he changes a line of code
- Fixed several bugs that were each individually humbling
- Wrote down every wrong turn in the notes so we don't walk into
  the same walls twice

### Known Quirks

- The clock doesn't handle daylight saving time. Twice a year, the
  herbs get an extra hour or lose one. They haven't complained yet
- Chrome really wants to use the secure version of the web (HTTPS).
  This tiny computer cannot do that. Type `http://` at the start
  of the address, or use Firefox, which is more relaxed about it
- If you manually toggle the light, the schedule will override you
  within a second or two. The schedule always wins. We may add a
  "I meant it" button later

## [0.2.0] - 2026-03-10

### First Light

- The chip is out of the bag. Literally — it came in an anti-static
  bag and now it is plugged in and blinking
- Successfully installed the operating system (CircuitPython) on a
  computer the size of a postage stamp
- The computer connects to our WiFi, asks the internet what time
  it is, and announces itself as `herbgarden.local` on the network
- Spent a meaningful portion of the afternoon discovering that our
  laptop's operating system has Opinions about who can talk to USB
  devices, and none of those opinions are helpful
- Tried to install two different terminal programs. Rebooted twice.
  One of them requires a Unix user group that doesn't exist on our
  computer and cannot be created. The other one works fine
- The operating system is "immutable," which is a polite way of
  saying it doesn't like being changed and will make you reboot
  to prove it

### Known Issues

- Need to open the grow light and check if it runs on 12V or 24V
  before wiring anything. Electricity is not a "find out" situation
- The web interface doesn't exist yet
- The light-switching transistor is still in its packaging, dreaming
  of its future career

## [0.1.0] - 2026-02-20

### The Planting

- Named the project **understory** — the shaded layer beneath the
  forest canopy, where light is managed. Also a good word
- The entire concept: one transistor, one schedule, one herb garden.
  A computer turns a light on in the morning and off at night.
  Everything else is ceremony
- Ordered parts from DigiKey. The transistor we picked is rated for
  55 amps. The grow light draws about 1. This is like hiring a
  bouncer for a library
- Added a safety diode because the grow light's power supply will
  throw a voltage tantrum when the transistor switches off. Physics
  is vindictive at small timescales
- Added a resistor to keep the transistor firmly off while the
  computer is booting up, because the computer's pins do a little
  dance at startup and we don't want the light flickering like a
  haunted house
- Drew the wiring diagram in LaTeX. Revised it seven times.
  Discovered that placing labels on circuit diagrams is a branch
  of mathematics that universities should offer degrees in
- Ordered spare components because breadboards are where small
  parts go to disappear
- The basil is alive. It has no idea any of this is happening
- Created the project. The branch is called `taproot`

### Known Issues

- Have not yet opened the grow light to check the voltage. See
  above re: electricity and "finding out"
- The web interface is a wish
- The ESP32 is still sealed in its anti-static bag, full of potential
- The schedule exists only as a feeling

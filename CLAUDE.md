# CLAUDE.md — rtk-base-station

Guidance for AI agents working in this repository.

## What this repo is

A permanent rooftop **RTK GNSS base station**. A u-blox ZED-F9P does all the GNSS
math; a SparkFun ESP32 connected over **I2C/Qwiic** acts as the network interface.
The project builds in three phases: (1) log 24 h of raw UBX observations and run
them through NGS OPUS for precise coordinates, (2) load those coordinates into the
F9P as a fixed position, (3) serve RTCM3 corrections to LAN rovers via a
self-hosted NTRIP caster.

Start with **`readme.md`** (full build/replication guide) and **`roadmap.md`**
(phased plan + live status). Real bring-up bugs are documented in `docs/issues/`.

## Layout

- `firmware/phase1_raw_logger/` — ESP32 sketch streaming raw UBX over WiFi/TCP
- `firmware/f9p_verify/`, `firmware/i2c_scan/` — bring-up / config-check sketches
- `receiver/ubx_receiver.py` — homelab TCP server that writes the `.ubx` capture
- `docs/issues/` — documented hardware/bring-up gotchas
- `readme.md`, `roadmap.md` — docs

## Rules

### Before pushing: verify no WiFi credentials are in any sketch

The ESP32 sketches contain `ssid` / `password` fields. These **must stay as
placeholders** in the repo — never commit real network credentials.

Run this check before every commit/push that touches `firmware/`, and abort if it
prints anything other than the placeholders `YOUR_WIFI_SSID` / `YOUR_WIFI_PASSWORD`:

```bash
grep -rnE '(ssid|password)\s*=\s*"' firmware/
```

If a real SSID or password appears, stop, replace it with the placeholder, and
inform the user — do not push. (A real `serverIP` LAN address is fine to commit;
WiFi credentials are not.)

### Other conventions

- **I2C, not UART.** The F9P ↔ ESP32 link is I2C over Qwiic. All sketches use the
  **SparkFun u-blox GNSS v3** library in I2C mode. Don't introduce UART-based code.
- **Read `docs/issues/` before touching wiring or I2C config** — board-variant,
  I2C-address, and bus-lockup bugs are documented there and are easy to re-hit.
- **Keep the receiver reconnect-resilient.** `receiver/ubx_receiver.py` loops on
  `accept()` with TCP keepalive so an ESP32 WiFi drop/reboot resumes into the same
  capture file. Don't regress it to a single-`accept()` design.
- **Keep docs in sync.** When phase status or hardware changes, update `roadmap.md`
  (status) and `readme.md` (build steps) in the same change. Add a `docs/issues/`
  entry when a new hardware gotcha is found.

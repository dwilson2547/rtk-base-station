# RTK Base Station

A permanent rooftop RTK GNSS base station that serves centimeter-accurate RTCM3
corrections to rovers on the local network via a self-hosted NTRIP caster. The
end result is a LAN-hosted correction source for 3D scanning, vehicle SLAM, and
robotics — no dependency on external services like RTK2Go.

The build runs in three phases:

1. **Phase 1 — Raw observation logging:** capture a 24-hour raw UBX file and
   submit it to NGS OPUS to derive precise base coordinates.
2. **Phase 2 — Fixed position:** load the OPUS coordinates into the F9P
   (`TMODE3 Fixed`) so it outputs corrections referenced to a known point.
3. **Phase 3 — NTRIP caster:** flash caster firmware and serve corrections to
   rovers on the LAN, permanently.

See **[`roadmap.md`](roadmap.md)** for detailed per-phase steps and current status.

---

## Repository layout

| Path | What it is |
|------|------------|
| `firmware/phase1_raw_logger/` | ESP32 sketch: enables RXM-RAWX + RXM-SFRBX on the F9P over I2C and streams raw UBX over WiFi/TCP to the receiver |
| `firmware/f9p_verify/` | ESP32 sketch that reads back every F9P config key and prints a pass/fail report (20 checks) — run this to confirm config survived a power cycle or firmware update |
| `firmware/i2c_scan/` | Minimal I2C bus scanner — first thing to run when bringing up the wiring |
| `receiver/ubx_receiver.py` | Homelab-side TCP server: writes the incoming UBX stream to a timestamped `.ubx` file, reconnect-resilient |
| `docs/issues/` | Write-ups of real bugs hit during bring-up (I2C addressing, bus lockup, wrong board variant) — **read these before wiring** |
| `roadmap.md` | Phased project plan and live status |

---

## Architecture

```
[ZED-F9P] --I2C / Qwiic--> [ESP32] --WiFi/TCP--> [receiver / NTRIP client]
   (all GNSS math)         (network interface)
```

The F9P is the brain — it does all GNSS computation and emits raw UBX (Phase 1)
or RTCM3 (Phase 3). The ESP32 is purely a network interface. In Phase 1 the
ESP32 is a **TCP client** pushing bytes to the receiver; in Phase 3 it is an
**NTRIP caster** that rovers connect to directly.

---

## Bill of materials

| Component | Part used | Notes |
|-----------|-----------|-------|
| GNSS receiver | u-blox ZED-F9P (SparkFun breakout) | L1/L2 dual-band RTK |
| Microcontroller | SparkFun ESP32 (Thing Plus) | Connected to F9P via **Qwiic (I2C)** — NOT UART |
| Antenna | SPK6618H | Multi-band, mounted on a pole, rooftop. Rebadged Harxon **HFX6618** — use that name for OPUS (step 3) |
| Power | PoE splitter | In a weatherproof roof enclosure |
| Backup | 1200 mAh LiPo | Rides out short power outages |

> **Critical — the F9P ↔ ESP32 link is I2C over Qwiic, not UART.** Every sketch
> here uses the **SparkFun u-blox GNSS v3** library in I2C mode. A UART-based
> sketch will not work with this wiring.

---

## Replication guide

### 0. Wire it up and verify the bus

Connect the F9P to the ESP32 with a Qwiic cable (I2C: SDA/SCL/3V3/GND). Then,
**before anything else, read [`docs/issues/`](docs/issues/)** — these three
bring-up bugs will each silently waste hours if you hit them blind:

- **[Wrong ESP32 board variant → I2C goes nowhere](docs/issues/2026_06_10_wrong_esp32_board_variant_i2c_pins.md)** — selecting the wrong board in Arduino sends all I2C traffic to unconnected GPIO.
- **[F9P I2C address / register encoding](docs/issues/2026_06_10_f9p_i2c_address_register_encoding.md)** — `CFG-I2C-ADDRESS` is the 8-bit value; setting `0x42` actually moves the device to 7-bit `0x21`.
- **[F9P I2C bus lockup from the RAWX buffer](docs/issues/2026_06_10_f9p_i2c_bus_lockup_rawx_buffer.md)** — the F9P holds SDA low after restart if its unread I2C output buffer fills with RAWX data.

Flash **`firmware/i2c_scan/`** and confirm the F9P shows up on the bus before
moving on. **`firmware/f9p_verify/`** can be run at any point to dump the full
config and check it against expected values.

### 1. Configure the F9P (u-center, one-time)

Connect the F9P over USB and apply these via u-center, then **save to BBR +
Flash** (`UBX-CFG-CFG`). `firmware/f9p_verify/` validates all of them.

**UBX-CFG-NAV5** — Dynamic Platform Model: `Stationary (2)`
**UBX-CFG-RATE** — Measurement Period: `1000 ms (1 Hz)`
**UBX-CFG-PRT (I2C)** — Protocol Out: `UBX only` (NMEA disabled on I2C)
**UBX-CFG-TMODE3** — `Mode 0 — Disabled` (correct for Phase 1; set to Fixed in Phase 2)

**UBX-CFG-GNSS** — all four constellations, L1 + L2:
GPS (L1C/A + L2C), GLONASS (L1 + L2), Galileo (E1 + E5b), BeiDou (B1I + B2I)

**UBX-CFG-MSG** — RTCM3 output on the I2C port (used in Phase 3; harmless in Phase 1):

| Hex ID | Message | Description | Rate |
|--------|---------|-------------|------|
| F5-05 | 1005 | Stationary ARP | 1 |
| F5-4D | 1077 | GPS MSM7 | 1 |
| F5-57 | 1087 | GLONASS MSM7 | 1 |
| F5-61 | 1097 | Galileo MSM7 | 1 |
| F5-7F | 1127 | BeiDou MSM7 | 1 |
| F5-E6 | 1230 | GLONASS code-phase biases | 5 |

> MSM7 over MSM4 gives full-resolution carrier phase, Doppler, and signal
> strength — worth the slightly larger messages.

### 2. Phase 1 — capture 24 h of raw observations

**a. Flash the logger.** In `firmware/phase1_raw_logger/phase1_raw_logger.ino`,
set your WiFi and the IP of the machine that will run the receiver:

```cpp
const char* ssid       = "YOUR_WIFI_SSID";
const char* password   = "YOUR_WIFI_PASSWORD";
const char* serverIP   = "192.168.0.55";  // host running ubx_receiver.py
const int   serverPort = 5555;
```

Dependencies (Arduino): board `esp32` by Espressif; library `SparkFun u-blox
GNSS v3`. On boot the serial console should show:

```
F9P connected
RXM-RAWX enabled
RXM-SFRBX enabled
WiFi connected: 192.168.x.x
TCP connected to 192.168.x.x:5555
Streaming... [bytes_sent] bytes
```

If it prints `F9P not detected`, recheck the Qwiic/I2C wiring and F9P power —
and revisit the issues in step 0.

**b. Run the receiver** on the homelab host (the one at `serverIP`):

```bash
python3 receiver/ubx_receiver.py
```

It listens on `0.0.0.0:5555`, writes `raw_obs_YYYYMMDD_HHMMSS.ubx`, and prints
progress every 60 s. It loops on `accept()` with TCP keepalive, so if the ESP32
drops WiFi or reboots it resumes into the same file rather than stalling:

```
Listening on 0.0.0.0:5555...
Output file: raw_obs_20260612_191614.ubx
Client connected from 192.168.x.x:xxxxx
[00:05:00] 1.76 MB received
[00:10:00] 3.51 MB received
...
```

**c. Verify data is actually flowing.** A healthy capture grows at roughly
**3.2 KB/s** (~280 MB / 24 h) with RXM-RAWX at 1 Hz. Don't trust "the process is
up" — confirm the **file size is increasing**:

```bash
ls -lh raw_obs_*.ubx        # size should climb every few seconds
```

> **Why this matters:** the original receiver accepted a single connection and
> blocked forever on it. When the ESP32 reconnected, the new connection piled up
> unread in the kernel backlog and the file silently stopped growing — a capture
> looked "running" for two days while collecting nothing. The current receiver
> fixes this, but always sanity-check the file size.

Let it run a full 24 hours before proceeding.

### Firmware updates over WiFi (OTA)

Once the board is mounted on the roof, reflashing it over USB is a pain. The roof
firmware therefore carries **ArduinoOTA** (`firmware/phase1_raw_logger/ota.h`), so
it can be reflashed over WiFi — most usefully to **swap between the raw logger (a
future re-survey) and the Phase 3 NTRIP caster** without a roof trip.

**The catch:** OTA only exists in the firmware that is *currently running*. You
must flash an OTA-capable build over USB **once** to bootstrap it; after that it's
network-only. And every roof firmware must keep the OTA hooks — flash a build
without them and you're back on the roof with a cable. The Phase 3 caster carries
its own copy of `ota.h` (hostname `rtk-base-ntrip`); keep the two in sync.

Before flashing, set the OTA password in `ota.h` (placeholder `YOUR_OTA_PASSWORD`,
never commit a real one). No partition change is needed — the board's default
scheme (`Default 6.25MB APP/OTA`) already has the dual app slots OTA requires.

```bash
# One-time bootstrap over USB (gets OTA onto the board)
arduino-cli compile --fqbn esp32:esp32:esp32thing_plus firmware/phase1_raw_logger
arduino-cli upload  --fqbn esp32:esp32:esp32thing_plus -p /dev/ttyACM0 \
  firmware/phase1_raw_logger

# Thereafter, push over WiFi — no USB:
arduino-cli upload  --fqbn esp32:esp32:esp32thing_plus \
  -p <esp32-ip> --protocol network firmware/phase1_raw_logger

# Which firmware is on the roof right now? Discover by mDNS hostname:
avahi-browse -rt _arduino._tcp   # rtk-base-logger vs rtk-base-ntrip
```

The board pauses its main loop during an upload — a brief capture gap for the
logger, a momentary corrections dropout for the caster. Both are harmless.

### 3. Phase 2 — OPUS coordinates → Fixed position

1. **Convert UBX → RINEX** with RTKLIB's `convbin`, built from the
   [rtklibexplorer fork](https://github.com/rtklibexplorer/RTKLIB)
   (`app/consapp/convbin/gcc && make` — no packaged binary). OPUS is **picky** —
   a plain conversion gets rejected three different ways. Use exactly this:
   ```bash
   convbin raw_obs_YYYYMMDD_HHMMSS.ubx -r ubx \
     -ro "-TADJ=1.0" -v 2.11 -ti 30 \
     -ts 2026/06/13 00:00:00 -te 2026/06/13 23:59:59 \
     -o observation.obs
   gzip observation.obs        # ~24 h @ 30 s ≈ 2.4 MB gzipped
   ```
   Each flag fixes a real OPUS rejection (see
   [`docs/issues/2026_06_15_f9p_clock_offset_opus_epoch_grid.md`](docs/issues/2026_06_15_f9p_clock_offset_opus_epoch_grid.md)):
   - **`-ro "-TADJ=1.0"`** — the F9P's clock is unsteered, so raw epochs sit off
     the integer-second grid (e.g. `:59.995`). OPUS requires epochs exactly on
     the grid; `-TADJ` snaps time tags to integer seconds *and* corrects the
     observations for the shift. (Without it, `-ti` also drops ~half the data.)
   - **`-v 2.11`** — convbin defaults to RINEX 3.04, which OPUS rejected as
     unrecognized. 2.11 is OPUS's bulletproof format.
   - **`-ti 30`** — decimate to 30 s (OPUS only uses 30 s; a full-rate 1 Hz file
     is "too much data").
   - **`-ts`/`-te`** — trim to a **single UTC day**. OPUS-Static allows ≤ 48 h
     crossing UTC midnight at most once; our 45 h capture crossed twice. Pick a
     day with full coverage.
2. **Submit `observation.obs.gz` to NGS OPUS** — https://www.ngs.noaa.gov/OPUS/,
   using **OPUS-Static**. Two field choices matter:
   - **Antenna type:** the **SPK6618H is not in the NGS list** — it's a rebadged
     Harxon **`HFX6618`**, which is. Select `HFX6618` (SparkFun's official
     substitute); it applies a real phase-center calibration, better than NONE.
   - **Antenna height: `0`.** You want the *antenna* (ARP) coordinate, not a
     ground mark — with a calibrated type + height 0, OPUS returns the ARP
     position with phase-center modeling applied, which is exactly what goes into
     TMODE3. A real height would yield a ground-reduced coordinate that, loaded
     into TMODE3, shifts every rover solution by that offset.

   OPUS emails back precise ECEF X/Y/Z + LLA in **two reference frames**
   (NAD83(2011) and ITRF2020). For a US base, use **NAD83(2011)** — rover
   positions then come out in the US standard datum. The two differ by ~1–2 m;
   don't mix them. Load the returned coordinate into TMODE3 **unchanged**.
3. **Enter the coordinates in u-center:** `UBX-CFG-TMODE3` → `Mode 2 — Fixed
   Position` → OPUS **NAD83(2011)** ECEF (or LLA) → save to BBR + Flash. Re-run
   `firmware/f9p_verify/` to confirm `CFG-TMODE-MODE` now reads `2`. Record the
   solution in [`coords.md`](coords.md).

> If the antenna is ever physically moved, Phase 2 must be redone.

### 4. Phase 3 — NTRIP caster

Replace the logger firmware with a self-hosted NTRIP **caster** (sketch lives at
`firmware/phase3_ntrip_caster/` once written). The ESP32 reads RTCM3 from the
F9P over I2C, handles the NTRIP HTTP handshake, and streams to rovers:

```
http://<esp32-static-ip>:2101/BASE1
```

Assign the ESP32 a static IP (DHCP reservation by MAC) so rovers have a stable
target, then point a rover's NTRIP client at the mount point above and confirm
it reaches RTK Fix. See `roadmap.md` Phase 3 for the full step list.

> **Don't use the SparkFun DIY GNSS tutorial sketch** — it implements an NTRIP
> *Server* that pushes to RTK2Go (out to the internet and back). For a
> self-hosted LAN caster that's an unnecessary external dependency.

---

## Key design decisions (settled — don't re-debate)

- **I2C, not UART** — SparkFun GNSS v3 library, file-buffer capture mode.
- **Self-hosted NTRIP caster** over RTK2Go — keeps corrections on the LAN, no
  internet dependency.
- **OPUS over survey-in** — PPP post-processing is significantly more accurate
  than survey-in averaging.
- **MSM7 over MSM4** — full-resolution carrier phase, worth the larger messages.
- **TCP push from the ESP32** (Phase 1) — the roof-mounted ESP32 is the client,
  avoiding NAT/firewall issues reaching a device behind WiFi.

---

## Current status

Phases 1 and the OPUS half of Phase 2 are **complete** — we have a precise base
coordinate (NAD83(2011), ≤ 8 mm peak-to-peak, 94% ambiguities fixed; see
[`coords.md`](coords.md)). **Next:** enter it into the F9P `TMODE3` Fixed
Position and verify. See `roadmap.md` for detailed state. Note: the F9P shipped
on firmware HPG 1.13; the latest is HPG 1.32 — consider updating before the
permanent Phase 3 install.

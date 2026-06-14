# RTK Base Station — Project Roadmap

## Phase 1 — Hardware Setup & Raw Observation Capture ✅

**Goal:** Capture a 24-hour raw GNSS observation file from the permanent antenna location and submit it to NGS OPUS to obtain precise base coordinates.

**Status: ✅ Capture complete. Ran 2026-06-12 19:16 → 2026-06-14 16:23 UTC (~45 h, well past the 24 h target) on devnode, file `raw_obs_20260612_191614.ubx` (505 MB). Converted to RINEX 3.04 with `convbin` → `observation.obs` (multi-GNSS: GPS/GLO/GAL/BDS/SBAS, dual-frequency). Gzipped to `observation.obs.gz` (136 MB), ready for OPUS submission.**

### What was built
- **`firmware/phase1_raw_logger/`** — ESP32 Arduino sketch that connects to the F9P over I2C, enables RXM-RAWX + RXM-SFRBX logging, and streams raw UBX bytes over WiFi/TCP to the homelab
- **`receiver/ubx_receiver.py`** — Python TCP server that writes the incoming stream to a timestamped `.ubx` file and prints progress every 60 seconds. Loops on `accept()` with TCP keepalive so an ESP32 WiFi drop/reboot resumes into the same file instead of silently stalling the capture
- **`firmware/f9p_verify/`** — verifier sketch that reads back all F9P config keys and prints a pass/fail report; all 20 checks currently pass

### F9P config locked in
- Navigation model: Stationary
- Measurement rate: 1 Hz
- TMODE3: Disabled (raw logging mode)
- Constellations: GPS L1+L2, GLONASS L1+L2, Galileo E1+E5b, BeiDou B1I+B2I
- RTCM3 rates on I2C: 1005, 1077, 1087, 1097, 1127 @ 1 Hz; 1230 @ 5 Hz

### Remaining step to close Phase 1
1. ~~Set WiFi credentials and homelab IP~~ ✅ serverIP set to devnode (192.168.0.55)
2. ~~Flash Phase 1 logger sketch~~ ✅ Running on ESP32
3. ~~Start Python receiver on homelab~~ ✅ Running on devnode, writing `raw_obs_20260612_191614.ubx`
4. ~~Let capture run 24 hours~~ ✅ Ran ~45 h, converted to RINEX, ready for OPUS — proceed to Phase 2

---

## Phase 2 — Precise Base Coordinate Entry

**Goal:** Use the OPUS-derived coordinates to lock the F9P into Fixed Position mode so it outputs RTCM corrections referenced to a known, accurate point.

**Dependencies:** Phase 1 capture complete

### Steps
1. **Convert UBX → RINEX** using RTKLIB's `convbin`. There's no packaged binary;
   build it from the [rtklibexplorer fork](https://github.com/rtklibexplorer/RTKLIB)
   (`app/consapp/convbin/gcc && make`), then:
   ```bash
   convbin raw_obs_YYYYMMDD_HHMMSS.ubx -o observation.obs -r ubx
   ```
   A 24 h 1 Hz multi-GNSS file produces a ~400 MB RINEX; `gzip` it before upload
   (compresses ~3×). OPUS accepts gzipped RINEX.

2. **Submit to NGS OPUS** at https://www.ngs.noaa.gov/OPUS/
   - Upload the `.obs` (or `.obs.gz`) file; use **OPUS-Static** (accepts 2–48 h)
   - **Antenna type:** the SparkFun **SPK6618H is not in the NGS antenna list**.
     It is a rebadged **Harxon HFX6618**, which *is* — select **`HFX6618`**
     (confirmed by SparkFun as the official substitute). This applies a real
     phase-center calibration, which is better than choosing NONE.
   - **Antenna height: enter `0`.** For an RTK base we want the coordinate of the
     *antenna* (ARP), not a ground mark. With a calibrated type + height 0, OPUS
     returns the ARP position with phase-center modeling applied — exactly the
     point that goes into TMODE3. Entering a real height would make OPUS report a
     ground-reduced coordinate; loading *that* into TMODE3 would shift every rover
     solution by the height offset.
   - OPUS emails back ECEF X/Y/Z + LLA coordinates with uncertainty estimates
   - Warren, MI has dense SE Michigan CORS coverage — expect a good solution

3. **Update F9P TMODE3 via u-center** (F9P USB on `/dev/ttyACM0`):
   - Open `UBX-CFG-TMODE3`
   - Set Mode to `2 — Fixed Position`
   - Enter OPUS ECEF coordinates (or LLA)
   - Save to BBR + Flash via `UBX-CFG-CFG`

4. **Verify fixed mode** with the verifier sketch — `CFG-TMODE-MODE` should now read `2` instead of `0`

### Notes
- The OPUS solution is significantly more accurate than survey-in averaging; do not shortcut with survey-in
- If the antenna is moved at any point after this step, Phase 2 must be redone
- Record the OPUS-derived coordinates in the project for reference (add to this file or a separate `coords.md`)

---

## Phase 2.5 — Independent accuracy validation against NGS CORS (planned)

**Goal:** Cross-check the OPUS-derived base coordinate against an independent
reference — the NGS CORS station in Warren, MI — to confirm our accuracy before
trusting the base for production corrections.

**Dependencies:** Phase 2 complete (OPUS coordinate in hand). Not yet performed.

### Why this is meaningful
OPUS already differences against ~3 nearby CORS (likely including Warren), so its
peak-to-peak figure is a consistency measure across the government network. This
phase adds an *independent* baseline solution as a second opinion. A short
baseline (our base and the Warren CORS are both in Warren — likely a few km)
makes it very precise: atmospheric errors largely cancel.

### Method — static baseline in RTKLIB
1. Download the **Warren CORS** RINEX for the same window as our capture (NGS
   UFCORS / CORS data page), plus the station's **published coordinates**.
2. In RTKLIB **`rtkpost`**, process a **Static** baseline: our base raw
   observations as rover, the CORS as the fixed reference at its published
   coordinates.
3. Compare the resulting base-antenna position to our OPUS coordinate.
   Agreement at **~1–2 cm** validates both; a larger gap points at antenna
   model, a bad epoch, or (most often) a datum/epoch mismatch.

### The datum/epoch gotcha (read before comparing)
CORS coordinates are published in **NAD83(2011)** *and* **IGS14/ITRF2014**, at a
specific epoch, with plate-motion velocities — and **NAD83 vs ITRF differ by
~1–2 m**. OPUS reports both. Compare apples to apples: same datum, same epoch.
A ~1 m disagreement is almost always this, not the hardware.

### End-to-end check (after Phase 3)
Once the caster is live, place a rover on a **published NGS passive mark** (the
NGS map lists these) and confirm the RTK-fixed position matches the published
value within a couple cm — this validates the whole chain (base + corrections +
rover), not just the base coordinate. Lighter variant: survey one point twice,
once via our base and once via Michigan's state CORS network (MDOT), and compare.

---

## Phase 3 — NTRIP Caster & Rover Integration

**Goal:** Replace the Phase 1 logger firmware with a self-hosted NTRIP caster so the base station serves centimeter-accurate RTCM3 corrections to rovers on the local network, permanently.

**Dependencies:** Phase 2 complete (F9P in Fixed Position mode with known coordinates)

### Architecture
```
[ZED-F9P] --I2C/Qwiic--> [ESP32] --WiFi--> [Rover NTRIP client]
                           :2101/BASE1
```

The ESP32 reads RTCM3 from the F9P over I2C and handles the NTRIP HTTP handshake, streaming corrections to any rover client that connects on port 2101. No external service or internet dependency.

### Steps
1. **Write NTRIP caster sketch** (`firmware/phase3_ntrip_caster/`)
   - Read RTCM3 messages from F9P via SparkFun GNSS v3 library (I2C)
   - Implement NTRIP caster protocol (HTTP/1.0 + sourcetable + data stream)
   - Mount point: `BASE1`
   - Port: `2101`

2. ~~**Assign static IP to ESP32** on the MikroTik DHCP server (bind by MAC)~~ ✅ Done — DHCP reservation in place

3. **Flash caster sketch** with WiFi credentials and static IP

4. **Test rover connection**
   - Point rover NTRIP client to `http://<esp32-static-ip>:2101/BASE1`
   - Confirm rover achieves RTK Fix status

5. **Weatherproof and install permanently** in rooftop enclosure with PoE power

### Important notes
- The SparkFun DIY GNSS tutorial sketch is an **NTRIP Server** (pushes to RTK2Go), not a caster. Do not use it — it routes through the internet unnecessarily.
- The ESP32 is purely a network interface; all GNSS computation stays on the F9P
- Consider adding a watchdog timer to the caster sketch so the ESP32 auto-recovers from WiFi drops or I2C lockups

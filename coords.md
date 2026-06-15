# Base Station Coordinates (OPUS-derived)

Precise coordinates of the rooftop base antenna's **ARP** (antenna reference
point), from NGS OPUS-Static. These are the values loaded into the F9P
`UBX-CFG-TMODE3` Fixed Position (Phase 2).

> **Antenna / height note:** submitted with antenna type `HFX6618` (the NGS
> calibration entry for the rebadged SparkFun SPK6618H) and ARP height `0.000`,
> so OPUS solved directly for the antenna reference point. Load these unchanged.

## OPUS solution — 2026-06-15

| | |
|---|---|
| Observation file | `base_jun13_24h.obs` (24 h, Jun 13 2026, 30 s, RINEX 2.11) |
| OPUS report file | `base1640.26o` / `OP1781484246061` |
| Ephemeris | `igu24226.eph` — **ultra-rapid** (data was recent) |
| Observations used | 43069 / 46938 (92%) |
| Ambiguities fixed | 272 / 288 (94%) |
| Overall RMS | 0.015 m |

### NAD83(2011) epoch 2010.0000 — **use this for TMODE3** (US standard datum)

| Axis | Value (m) | Peak-to-peak (m) |
|------|-----------|------------------|
| X | `571942.275` | 0.006 |
| Y | `-4672191.750` | 0.005 |
| Z | `4289770.788` | 0.008 |

- LAT: `42 32 9.68010` N (0.003 m)
- W LON: `83 1 15.27600` (0.005 m)
- Ellipsoid height: `157.847` m (0.008 m)
- Ortho height: `192.386` m [NAVD88, GEOID18]

### ITRF2020 epoch 2026.4479 (global frame — for reference only)

| Axis | Value (m) | Peak-to-peak (m) |
|------|-----------|------------------|
| X | `571941.248` | 0.006 |
| Y | `-4672190.381` | 0.005 |
| Z | `4289770.736` | 0.008 |

> **Datum choice:** load the **NAD83(2011)** ECEF into TMODE3 — rover RTK
> positions then come out in NAD83(2011), matching US survey control, the CORS
> network, and GIS/maps. The two frames differ by ~1–2 m (plate motion); don't
> mix them. See `roadmap.md` Phase 2.5 for the datum/epoch caveat.

## Validation reference (Phase 2.5)

OPUS lists **Warren CORS (PID DG9785)** as the nearest published control point,
**227.2 m** from our antenna — and it was *not* one of the three base stations
OPUS used (MIFW Fort Wayne 27 km, MIWA Romeo 27 km, MILI Livonia 34 km). That
makes Warren CORS a fully independent ~227 m baseline for the Phase 2.5 check.

## Notes

- Solution used **ultra-rapid** orbits because the data was only 2 days old.
  Peak-to-peak is already ≤ 8 mm, so this is fine to use. Optional polish:
  resubmit the same file in ~2 weeks once IGS final orbits post, to lock in the
  definitive coordinate (re-running TMODE3 is trivial).
- If the antenna is ever physically moved, this entire process must be redone.

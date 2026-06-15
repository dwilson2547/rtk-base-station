# F9P raw epochs sit off the integer-second grid (unsteered receiver clock) → OPUS rejects, decimation drops data

**Date:** 2026-06-15
**Component:** Phase 1 → Phase 2 workflow — `convbin` (UBX → RINEX), OPUS-Static submission
**Severity:** High — blocks the OPUS solution entirely; also silently corrupts naive time-grid decimation

---

## Observed symptom

Two separate failures, same root cause:

1. **`convbin -ti 30` produced huge fake gaps.** Decimating the 45 h, 1 Hz capture to 30 s with `-ti 30` yielded only ~2200 epochs (expected ~5400) with three multi-hour "gaps" totalling ~27 h — even though the full-rate 1 Hz file was verified **continuous with zero gaps** (162,428 epochs, no step > 5 s).

2. **OPUS aborted (error 1020, reason #2):** *"The time of each epoch is offset from one of the allowed intervals. The seconds epoch field must coincide with one of the above rates."* The submitted RINEX had `TIME OF FIRST OBS = ...:59.9950000` — epochs landing at `:59.995`, `:29.995`, etc. instead of exactly `:00.000` / `:30.000`.

---

## Root cause

The SparkFun ZED-F9P's receiver clock is **unsteered** — it free-runs and drifts rather than being disciplined to GPS time. `RXM-RAWX` reports `rcvTow` (the receiver's local time of week), so every measurement epoch is offset from the integer-second grid by the current clock bias. Over this capture the offset drifted across roughly ±0.5 s.

Consequences:

- **OPUS** requires each epoch's seconds field to coincide *exactly* with the sampling grid (`:00.0000000` / `:30.0000000` for 30 s data). Off-grid epochs are rejected outright.
- **`convbin -ti`** decimates by matching epochs to a fixed time grid within a small tolerance (`-tt`, default 0.005 s). Wherever the clock bias drifted away from an integer second, *no* epoch fell within tolerance of a 30 s mark, so convbin dropped the entire stretch — producing the fake gaps. (The full-rate file keeps every epoch regardless of offset, which is why it looked clean.)

A naive fix — relabeling epoch timestamps to the grid — is **wrong**: the observations were physically measured at the off-grid time, so carrier phase would be off by `phase_rate × Δt` (meters). The epoch must be *shifted*, adjusting observations via their range rates (Doppler), not merely relabeled.

---

## Troubleshooting steps taken

1. **Gap analysis on the full-rate RINEX** — 162,428 epochs, zero gaps > 5 s over 45.1 h. Established that the capture itself was perfect and the "gaps" were a conversion artifact.
2. **Inspected epoch fractional seconds** — found values like `:59.995` and a drift across ±0.5 s; correlated the convbin dropouts with stretches where the offset sat near 0.5 s. Identified the unsteered clock as the cause.
3. **Confirmed OPUS rejection was the same issue** — error 1020 #2 (epoch seconds must coincide with the rate), matching the off-grid timestamps.
4. **Checked convbin options** — no epoch-snap/clock-align flag exists; `-tt` is only a match tolerance.
5. **Applied RTKLIB receiver option `-TADJ`** — snaps time tags to a clean interval *and* corrects observations for the shift. Resolved both problems in one pass.

---

## Fix

Add the RTKLIB receiver option **`-ro "-TADJ=1.0"`** to the `convbin` call. It rounds u-blox time tags to integer seconds (`TADJ` = adjustment interval) and adjusts the pseudorange/carrier observations for the time difference. Run it *before* the `-ti` decimation so the on-grid `:00` / `:30` epochs exist to be selected.

```bash
convbin raw_obs.ubx -r ubx -ro "-TADJ=1.0" -v 2.11 \
  -ts 2026/06/13 00:00:00 -te 2026/06/13 23:59:59 -ti 30 \
  -o observation.obs
```

Result: `TIME OF FIRST OBS = 00:00:00.0000000`, every epoch at exactly `:00.0000000` / `:30.0000000`, a **full continuous 2880-epoch day** (no fake gaps), accepted by OPUS.

This fix combines with the other OPUS submission requirements (see `readme.md` Phase 2):

- **RINEX 2.11** (`-v 2.11`) — the 3.04 file convbin emits by default was rejected as unrecognized.
- **Single UTC day** (`-ts`/`-te`) — OPUS allows ≤ 48 h crossing UTC midnight at most once; the 45 h capture crossed twice.
- **30 s, on-grid** — this fix.

---

## Files changed

- Documentation only — `readme.md` and `roadmap.md` Phase 2 recipe updated with the `-TADJ` / RINEX-2.11 / single-day workflow. No firmware change (the F9P capture is correct as-is; this is a post-processing conversion fix).

## Future option

For an even cleaner future capture, the F9P could be configured to steer its clock, but it is not required — `-TADJ` handles the existing data correctly.

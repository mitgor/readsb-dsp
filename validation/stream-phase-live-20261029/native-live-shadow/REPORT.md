# Native phase repair: 30-minute live shadow audit

**Decision: keep phase repair shadow-only.** The observer found many candidates
beyond the current unified FR24 feed, but the experiment does not establish a
false-positive rate or exact independent packet truth. No repaired output was
sent to FR24. The original rescue shadow command was restored after the run.

## Live comparison

The research service read only the existing nonblocking IQ mirror, stock Beast
and unified Beast streams on the Pi 5. It ran for 1,801 wall seconds and
completed **1,705 paired RF seconds** (94.7% of the wall interval). It had no
decoder errors, no research queue-shed seconds and no incomplete unified
comparison windows. The first 40%-of-one-core CPU ceiling throttled the
research process and caused most of its 361 IQ discontinuities. Raising only
that ceiling to 80% stopped sustained research gaps; low scheduling priority
remained. The production tap-drop counter showed a small 5,536-sample increase
during the run and stayed flat after that adjustment. Stock reception and
FR24 stayed active with fresh traffic. The later rescue-shadow restart used
to restore its original command caused a separate short tap gap.

On the paired seconds, the native observer found **4,990 CRC-valid DF17
candidates absent from the actual unified feed within 120 µs**:

| Native kind | Unified-absent candidates |
|---|---:|
| Clean phase | 290 |
| CRC table repair | 1,558 |
| Confidence erasure repair | 3,142 |

The range bins use a fresh position from the local stock receiver. There
were 479 candidates at 0–50 nm, 1,597 at 50–100, 2,164 at 100–150, 255 at
150–180, **35 at 180–200**, none at 200+ and 460 with unknown range. This
traffic sample cannot establish a far-range gain.

## Corroboration and negative control

The Mac helper's separate stock/unified Beast capture closed cleanly. The
strict audit found all 4,990 logged events within its complete paired
coverage; no event overlapped stock or unified at its claimed transmission
time. **1,899** of these payloads appeared exactly in stock later within 30
seconds. This is useful same-receiver support for those messages, not an
independent receiver or proof for the others. Beast omits readsb's corrected
bit count, so the observer's prior-ICAO bitmap is a permissive approximation
of the production guard.

Forty successful adsb.fi polls provided external aircraft track context
(source: [adsb.fi](https://adsb.fi), personal non-commercial research).
An aircraft with the same ICAO had a fresh reported position for **3,532**
candidates. Of the 3,237 with both external and local range bins, **3,191
(98.6%)** bins agreed. A matching ICAO/position is not independent evidence
that the corrected payload bits are true. The public network can also contain
data derived from other aggregators; we did not obtain an independent raw Beast
frame from a separately identified receiver.

In a 300-second uniform-random-IQ negative control, with a permissive bitmap
of 3,236 historically seen ICAOs, the decoder admitted **4 clean, 1 table and
14 erasure** CRC-valid candidates. This noise is not a realistic RF
false-positive model, but it directly disproves the assumption that CRC plus
known ICAO alone authenticates a repair. It also counsels caution with clean
phase candidates in any future canary.

## Operational result and next gate

`readsb`, `fr24feed`, `adsb-rescue-feed` and `adsb-rescue-shadow` were active
after rollback; the FR24 relay reported fresh stock, no upstream error and
Broad CRC still excluded. The research service exited successfully and is
disabled at boot. The temporary `95-native-phase-mirror.conf` drop-in was
removed; the effective shadow command again ends with the pre-existing
`--mac-helper-socket` option. Only research files remain under `/run` and the
staged source/library on the Pi; none has a feeder connection.

The next gate is **independent exact-packet evidence** from another receiver
or a validated physical/signal model that can bound false repair admissions.
Until then, do not forward table or erasure repairs and do not claim the
4,990 candidates as verified reception improvement. Clean phase output also
needs a stricter canary gate. The local raw IQ, Beast and candidate event logs
are retained outside Git; `public-summary.json` contains only aggregates.

The implementation and rollback procedure are in
[`docs/LIVE_PHASE_SHADOW.md`](../../../docs/LIVE_PHASE_SHADOW.md).

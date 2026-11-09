# Guarded DSP expansion — 9 November 2026

User requested remaining DSP methods, including acquisition, sequence and pulse,
provided processing stays inside the existing three-second relay budget.

1. Inspect live source/configuration and preserve the previous production profile.
   Validate the deployed pulse model/native implementation and archive headroom.
2. Apply both method/worker config files with one DSP-shadow restart. Preserve
   readsb, FR24, relay, ADSBx and RF collector processes. Keep gain, models,
   libraries, RF cap and feed admission rules unchanged.
3. Observe fresh live processing and guarded relay output. Keep a persistent
   ten-second monitor with a300ms latency margin and automatic profile rollback.

Attempt v1 enabled every implemented branch. Worker latency reached2.5726s,
before Stream1090. The guard restored the previous profile when its latency
margin was exceeded. Header retry was the largest added attributed CPU cost in
that short run. This is not a formal per-method ablation or proof that every
all-method job exceeded3s.

Attempt v2 excludes header retry while enabling SIC, pulse, sequence and
acquisition alongside the existing energy/timing/soft/matched/coherent/neural/
Stream1090 profile. Broad CRC research remains quarantined, never feeder input.
Only existing implementations and validated models are selected.

`guard.py` is installed in `/var/lib/adsb-all-methods-20261109-v2` and checked by
`adsb-all-methods-budget-20261109-v2.timer`. It compares the recent maximum worker
result/queue latency with the latest integrated Stream1090 cost; this is a
conservative sampled proxy, not exact per-packet end-to-end instrumentation.
At2.7s, stale worker status, increased radio sample loss or sustained feeder
failure, it restores the recorded former profile and restarts only DSP shadow.
The relay independently rejects candidate packets past its hard3-second
sample-clock admission deadline. A ten-second monitor cannot promise zero
transient deadline misses. It refuses to overwrite a subsequent human config
change and stops monitoring if ownership is superseded. No automatic retry loop.

`activate.py --attempt v2 --exclude header` is the recorded activation command;
it refuses to overwrite an existing attempt. `observe.py --attempt v2` records
live observation into the private data workspace. Do not rerun an observer into
its existing output or overwrite original evidence. The activation’s ordinary
graceful shutdown preserves the existing CRC RAM archive; no saved archives are
deleted or caps raised. Main logging remains off as before; RF capture stays on.

Five policy/ownership tests pass. Private snapshots retain both attempts and
source/config backups. See `validation/all-methods-20261109/summary.json` for the
final observed condition. This operational check does not establish net recovery
against a frozen stock/full-pipeline RF replay or FR24 cloud-credit improvement.

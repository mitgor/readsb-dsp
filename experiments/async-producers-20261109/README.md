# All-source asynchronous integration — 9 November 2026

Experimental path only. No production method, model, decoder, library, relay,
feeder route, gain, capture cap or service restart. Current production continues
its three-second relay. All outputs from this integration remain quarantined.

`integration.py` consumes raw completed worker futures without pre-deduplicating
seams, plus an independent Stream1090 future launched from the same whole RF
window. `Admission` reuses the current receiver's exact evaluate/CRC/address/
conflict/clock-alignment policy with causally available stock and energy anchors.
`SourceHub` has independent bounded source queues and one shared final
five-second/120us transmission cache. Stock is immediately serialized, unchanged;
there is no global RF timestamp sort or source-completion wait. Subsequent stock
always survives, including late-stock-after-extra races. Radio epoch is taken
from original RF batch metadata; restart clears anchors and rejects old futures.
Broad CRC and disabled methods are never routed.

Closely coupled methods still share their C/Rust/frontend computation and can
finish together. Independence means completed groups do not wait for unrelated
futures or Stream1090, not that shared computation is redundantly rerun for every
source. The unchanged grouping path still supplies comparison/statistics results.

## Two complementary checks

1. `observe_live.py` is a finite read-only adapter for all actual admitted producer
   outbox notifications. It queues each source independently and compares the
   complete original stock bytes and method cohort with current combined31005.
   It preserves current whole-second producer grouping, and cannot prove earlier
   within-producer latency. An existing250ms profile is a deliberately restrictive
   negative control; the compatibility profile keeps the current3s RF age limit.
2. `replay.py` connects actual current DSP/Rust/neural futures and independent
   Stream1090 decoding to the new hub using16 fresh RF windows. It compares against
   unchanged grouped full-pipeline decoding, recorded accepted-production batches
   and actual relay records on identical samples, with one-to-one transmission
   matching. Original grouping exactness, lost extras, duplicate extras, stock
   matches and independent Stream1090 reference filtering are audited.

Only the idle optional mirror was briefly armed, refusing an existing owner and
retaining a unique heartbeat token until producer journals closed. Original IQ,
stock, relay and accepted-producer context are checksum-backed privately. All
captured intervals, including the failed capture attempt, are globally reserved
as evaluation-only before replay. The successful capture has one RF-copy gap;
only the16 captured one-second core windows are compared, never interpolated.
RF/Beast and positions are private, not supervised labels or public artifacts.

## Reproduce safely

Use the existing project Python and the **captured receiver runtime** in PYTHONPATH.
The canonical older src tree lacks the deployed Stream1090 admission extension;
do not substitute it and silently lose a method. Models and source/library hashes
are verified. Mac uses compatible native Mach-O libraries; Pi uses exact copied
production Rust/native libraries and current model hashes.

`start_capture.py`, `fetch_capture.py`, `start_observer.py`, `fetch_observer.py`,
`prepare.py`, `start_replay.py`, `protected.py` and `fetch_pi.py` record the owned finite stages.
Fixed paths refuse overwriting prior attempts. Do not rerun them over preserved
outputs; create another dated attempt. Keep the working pipeline unchanged.

Pi replay uses nice19/core3/35%one-core quota/1GiB/finite runtime. Its RF clock is
slowed12x to test functional integration without stealing production CPU; this
is **not proof of real-time Pi latency**. Protected PIDs, models/libraries/configs,
gain, sample loss, collector health and feeder connectivity are monitored. Only
the owned replay is stopped if protected health changes.

The first target harness used non-executable /run and failed before processing.
A second lost pi-owned multiprocessing semaphores. The retry keeps copied code
in root-owned executable tmpfs under established sudo, without changing mount,
IPC, access or network settings. A quota-limited run then lost five extras on one
Stream1090 timeout. The final coordinator caches unchanged stock snapshots and
polls without burning the quota; decoder parameters and the one-second Stream1090
timeout are unchanged. Failed and intermediate evidence is preserved. Repeated
engineering checks on these same RF windows are not independent prospective
validation or model training.

See validation/async-producers-20261109/report.md and summary.json for results
and explicit deployment limits. No production activation is part of this task.

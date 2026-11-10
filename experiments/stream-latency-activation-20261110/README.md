# Activate the incremental Stream1090 pipeline on the existing Pi profile

This release connects the four validated `stream-latency-v2-20261110` components
to the existing rescue coordinator. It is opt-in; the generic repository defaults
remain unchanged. `patch.py` applies narrowly scoped hooks to the current Pi
profile, which already has Stream1090 and the normal shared-ring DSP workers.
It refuses missing or ambiguous source anchors. `deploy.py` also requires the
exact preflight source SHA-256 before replacing the coordinator file.

- The existing copied IQ datagrams feed a bounded decoder thread in 20 ms chunks.
  It runs on the existing DSP core set (2 and 3 on this profile). It never opens
  the SDR or binds a new mirror socket. Raw logical windows and trust resets keep
  their original one-second boundaries and 600-sample halos.
- The completion tap observes the original DSP futures, even when the ordered
  grouping consumes them during the same poll. It publishes all energy rows from
  the actual workers, including stock-matching alignment anchors. Other DSP and
  neural work is not re-run or moved. Shared input receipts are buffered until
  their verified RF epoch is ready, and delivered in block ownership order.
- Rust admission and the shared five-second early transmission cache retain the
  same CRC, clock, stock identity, conflict and duplicate requirements. Early
  files carry their actual verified alignment audit. Pending slices retry on
  causal evidence. Context freshness is checked before early publication.
- A missing completion cannot pin the queue indefinitely. After four later RF
  seconds the old early context retires. The complete grouped comparison, capture
  ledger and original executable fallback remain available. The first guarded
  live attempt exposed this startup case and reverted; the final replay explicitly
  exercises the retirement and no-resurrection behavior.

The existing relay retains its normal stock handling, acceptance, stock-first
rechecks and three-second ordering holdback. Whole-window batches still reach it:
publication to the early outbox does not prove relay acceptance and cannot be
used to suppress their fallback. The relay deduplicates against its own accepted
transmissions. The short test-socket latency improvement does not establish FR24
upload latency. Full-window attribution and capture/training records still follow
the existing complete comparison, even when an extra was published earlier.

The private stage contains `shadow-original.py`, the patched coordinator and
modules in `runtime/rescue/`, the four verified libraries in `bin/`, the reserved
saved-RF fixture and a checksum manifest. `preflight.py` runs the actual bridge
and outbox code in an isolated tmpfs under the existing Pi limits. The gate
requires retention of all 79 energy/Stream1090 extras and matching membership of
all 210 recorded complete-pipeline transmissions, plus fallback, completion
and incomplete-window controls. It does not use live feeder output as a test sink.

`deploy.py` uses the established native guard's health/capacity helpers. It saves
the original coordinator, installs the manifest-matched components and restarts
only `adsb-rescue-shadow`. The original executable path remains available in the
running process. Readsb, both feeders, the relay and the far recorder stay up.
There can be a copied-IQ gap during a coordinator handover. The normal graceful
CRC cache save must fit before a restart; no archive deletion is needed.

The independent systemd timer checks readiness, component/config hashes, RF
progress, sample-loss counters, protected service health and the 5 GB capture cap.
Two bad checks disable the opt-in path and restore the original coordinator file.
A healthy running coordinator falls back in place; a dead or stalled one is
restarted. Concurrent source edits are preserved. Manual rollback:

```sh
sudo /usr/local/sbin/adsb-stream1090-lowlatency-mode rollback --reason manual
```

`rollback_controls.py` tests restore, concurrent edit preservation and the
second-strike trigger with no real service operations. Raw RF, packet-level
results, private snapshots and rollback copies stay in the private workspace.

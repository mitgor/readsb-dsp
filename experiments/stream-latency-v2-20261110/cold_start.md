# Bounded cold-start retries

Use `Bridge(epoch, emit, admission=engine, retry=ColdStartRetry())` in the isolated
completion experiment. The helper owns no socket, RF, production setting, decoder
or admission rule. It only chooses which already-pending 20 ms slices should be
checked again. It never labels or accepts a packet.

The old path could permanently skip a slice when its first energy audit lacked
20 matches, leaving it until the one-second finalization fallback. The completion
bridge instead retains that slice. When later native, energy or stock **has
actually arrived**, the bridge advances its evidence revision and causal coverage.
The helper selects eligible older slices once for that new revision. The existing
admission engine must still verify the unchanged CRC, alignment, stock-only prior
identity and conflict guards. Later RF evidence is usable only after completion;
it is not supplied from the future or inferred from elapsed time.

API:

- `select(window, pending, evidence_end_tick, revision_tuple, now_s)` returns stable
  ascending indices. `pending` is the complete current map `{index: (lo, hi)}`.
  The bridge supplies `(stock_revision, energy_revision, native_revision)`.
- `resolved(window, index)` records guarded success or an empty slice and prevents
  replayed pending entries from causing a second attempt.
- `close(window)` releases active state after the unchanged finalization fallback.
- `reset()` clears all retry state on an externally verified RF epoch change.
  The bridge, not this helper, validates incoming epoch values.

Defaults are 16 active windows, 50 slices per window and 800 pending slices total.
Over-cap input fails before changing state; active work is not silently evicted.
Closed-window tombstones are bounded to twice the active-window limit. The bridge
must reject late results for finalized or old-epoch windows independently.

A larger wall clock without a new evidence revision does not cause another
attempt. Coverage beyond the arrived watermark does not authorize a slice.
Backwards evidence revisions, coverage, completion time or changed pending RF
identity are rejected. Failed admission never calls `resolved`; the slice remains
pending until better causal evidence or the original finalization fallback.

Run synthetic state tests with:

```sh
python cold_start_tests.py
```

These controls do not demonstrate RF recovery or real-time Pi performance; those
remain the parent experiment's identical-RF retention and latency benchmark.

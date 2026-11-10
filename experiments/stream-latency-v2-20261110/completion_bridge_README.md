# Event-driven completion bridge

`completion_bridge.py` is isolated experimental code. It owns no socket, SDR,
production configuration, feeder output, model or worker process. The caller
supplies completed producer results and a causal stock snapshot, and its output
callback must enter the separate final validated transmission deduplicator.

```python
bridge = Bridge(epoch, emit, admission=native_admission, retry=cold_retry)
bridge.begin(key, case)  # case contains integer first sample and optional epoch
bridge.on_stock(frame)  # appends the native admission index exactly once
bridge.offer(key, "native", epoch, rows, complete_watermark, done)
bridge.offer(key, "energy", epoch, owned_rows, complete_watermark, done)
bridge.drain(stock_history.snapshot(), stock_watermark, elapsed_seconds)
```

Use `notify_stock()` instead of `on_stock()` only when another owner has already
appended the native stock index. The caller must not append the same stock frame
both ways. Native rows are `(ticks, message_hex)` tuples. Energy rows are original
validated candidate dictionaries with source `energy` and single ownership in
this logical window's RF core. A conservative watermark can trail already
decoded candidates: rows are retained until complete slice coverage catches up.

An energy adapter must release results only at their actual/simulated causal
completion times. The bridge never reads future producer results. All stock
frames in the snapshot and native index must likewise have already arrived.
The callback is `emit(row, alignment_audit, elapsed_seconds, lane)` where lane is
`early` or `final`. All returned outputs remain subject to the final stock-only
prior/conflict/RF-age checks and shared Rust five-second deduplicator.

Producer completions and stock changes mark bounded active subscribers dirty.
`drain` consumes that event generation once. Repeated idle calls do not evaluate
clocks, revisit windows or re-run admission. Native clock offsets use the original
same-payload ten-match calibration and are fixed inside a one-second logical
window. The complete currently available reference rechecks the offset at final
closure; a shift larger than the original 24-tick allowance fails the experiment.

When a 20 ms slice first lacks the original 20 energy alignment matches, it stays
pending. A later *already arrived* energy completion can provide the required
anchors, ending at the minimum completed native/energy/stock frontier minus the
original 120 us completion guard. This does not consult future completions or
lower CRC, identity, conflict or alignment thresholds. The native admission
engine still makes every packet admission decision. Finalization reuses cached
native rows and original per-window energy rows; it does not decode RF again.
Both early and final publications enter the same final deduplicator.

Retry policy is injected via these methods:

- `select(window, pending, evidence_end_tick, revision, now_s) -> indices`
- `resolved(window, index)`
- `close(window)`

Here `pending` maps integer slice index to `(lo_tick, hi_tick)`, and `revision` is
`(stock_revision, energy_revision, native_revision)`. Failed slices remain pending;
verified and empty slices resolve. The default `EvidenceRetry` retries each pending
slice at most once per changed causal evidence revision. `ColdStartRetry` can
supply the explicitly bounded audited policy without changing packet validation.

Active window count, candidate count and energy evidence count are bounded. A
cap failure raises instead of silently evicting active work. Finalized windows
may be evicted to make space. Wrong epochs, invalid CRC, out-of-core energy,
backward watermarks and closed-source completions fail closed. The calling
finite supervisor owns any fault containment and quarantine of experimental RF.

## Controls

Run `completion_bridge_tests.py` in the existing project environment with the
copied production runtime on PYTHONPATH. `--library /path/to/native-admission.so`
runs the same controls using both Python and native admission. The tests cover
causality, preserving cold slices, no idle work, early retry without finalization,
wrong epoch, invalid CRC, backward watermarks, final fallback, late completions,
active window limits and result-count bounds. They open no receiver or feeder.

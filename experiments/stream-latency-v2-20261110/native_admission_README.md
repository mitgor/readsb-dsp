# Experimental native admission

`native_admission.rs` ports the existing `rescue.shadow.evaluate` admission
function to Rust, with persistent bounded stock indexes. It has no socket, SDR,
wall clock, model, packet repair or production configuration access. Candidate
output is quarantined. This is not a replacement live service.

The caller appends stock frames **only after they arrive**, in arrival order.
Stock must be canonical lowercase CRC-valid DF17, matching the existing stock
parser contract. Stock arrival eviction and RF timestamp order are separate,
just as in `StockHistory`. The default 100,000-frame bound is configurable up to
1,000,000; reset clears stock evidence and starts another RF epoch.

All twelve existing source priorities are supported, in their original order:
energy, timing, soft, matched, coherent, sequence, acquisition, pulse, header,
SIC, neural and Stream1090. The following semantics are unchanged:

- Energy alignment requires >=20 matches; median absolute error <=24 12 MHz
  ticks, with only errors <12,000 ticks admitted to the median.
- DF17 CRC validation, conservative same-transmission matching within 1,440
  ticks, stock-only prior identity within 360,000,000 ticks, and conflicting
  stock payloads within +/-48 ticks.
- Neural candidates matching any valid energy candidate within 1,440 ticks are
  excluded before ordinary duplicate checks.
- Source/timestamp sorting is stable; accepted candidates update only temporary
  per-call duplicate indexes, never the authoritative stock identity history.
- `start` and `stop` do not filter candidates, matching the original function;
  the caller owns core filtering after evaluation.

Internal timestamps are exact **quarter 12 MHz ticks**, preserving fractional
DSP timing/matched candidates (.25/.5/.75 ticks) without rounding. The wrapper
returns original candidate dictionaries, including their original timestamp
values and metadata. Finer timestamps and noncanonical uppercase payloads fail
closed instead of silently changing their interpretation. Invalid candidate CRCs
and malformed payloads still contribute the original `invalid` decision when
alignment is verified. Unknown sources are filtered before their unused fields
are read. The stock watermark is the maximum RF timestamp seen since epoch reset,
not arrival time or a packet-source priority change.

The 24-byte row and audit ABIs are asserted at load time. Native calls have
bounded input capacities, wrong-epoch checks, output-capacity checks and zero
output count on failure. Single-owner operation is required: append/evaluate
must be serialized. Candidate outputs remain owned by the caller.

## Build and call

No new dependencies or installed service are required:

```sh
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=abort \
  native_admission.rs -o /owned/private/tmp/native_admission.so
```

```python
from native_admission import NativeAdmission
with NativeAdmission(library, maxlen=100000, epoch=epoch) as admission:
    admission.append_stock(arrived_frame)
    output, audit, counters = admission.evaluate(candidates, start, stop)
    watermark = admission.latest_stock_tick
    admission.reset(new_epoch)
```

`append_stocks(frames)` is an optional bulk interface. No Python stock-history
snapshot or all-payload dictionary copy is needed for an evaluation. The same
stock-only snapshot can still be maintained by the experiment for independent
native clock-calibration parity.

## Validation

Use the existing private Python environment and copied production runtime:

```sh
PYTHONPATH=/copied/runtime OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /existing/python native_admission_tests.py --library /private/native_admission.so \
  --output /private/new-controls.json --capture /private/reserved/capture
```

The tests compare output dictionaries, alignment audit and all counters exactly
against production `shadow.evaluate`, using synthetic controls, randomized
bounded arrival eviction/out-of-order RF, and actual same-I/Q energy frontend
results from the reserved eight-second historical capture. Real stock arrivals
are applied causally for each energy-prefix check. Recorded other-DSP producer
rows have no per-method completion times and are used only for explicit deferred
parity checks, never as early anchors or training labels. The tests do not
constitute new prospective range evidence.

## Python marshalling optimization

The Rust guards and library are unchanged by the wrapper optimization. A bounded
8,192-entry FIFO cache stores **only immutable 24-byte encodings** keyed by
timestamp type/value, payload and source. It never caches an admission result,
identity decision, stock reference or original candidate dictionary. Epoch reset
and close clear it. Candidate metadata changes therefore still return the
current original row. Encoding reuse cannot authorize a packet without the
current Rust stock/CRC/alignment/conflict checks.

Cached encodings are concatenated and copied once into an aligned ctypes input
array. Selected-index, audit and counter output buffers are reused, bounded by
the existing 100,000-candidate limit. The API and single-owner requirement are
unchanged. The full parity suite includes cache eviction, metadata mutation and
stock evidence arriving after a previously rejected encoding was cached.

`native_admission_marshalling_bench.py` compares the uncached wrapper with this
wrapper against the identical native library. The 4-repeat, alternating-order
Mac microbenchmark uses 24, 100 and 260 repeated-anchor candidate rows: total
evaluate CPU fell by approximately 54%, 56% and 62%; marshalling alone fell
85–88%. These are synthetic wrapper costs, **not** whole-pipeline RF throughput
or Pi latency measurements. The old wrapper and measured arrays are preserved
privately; the integrated RF/Pi study remains the deployment gate.

For a reproducible wrapper comparison, pass the included
`native_admission_reference.py` to the microbenchmark's `--baseline-python`
argument. It preserves the original uncached adapter; both wrappers use the
same Rust library and the same guard rules.

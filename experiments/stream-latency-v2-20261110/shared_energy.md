# Shared energy completion adapter

`shared_energy.py` is an isolated, in-memory adapter for sharing **all original
CRC-valid energy candidates before stock/admission filtering**, including energy
packets already decoded by stock. Those matching packets are needed as timing
anchors. The old producer journal of *accepted extras only* is insufficient and
must not be used as a replacement. There is no decoder, model, socket, mirror,
receiver access, production configuration change or feeder output in this module.
The downstream admission guard remains responsible for CRC and trust checks.

## Existing producer integration

```python
from shared_energy import SharedEnergyFeed, completion_from_block

feed = SharedEnergyFeed(epoch, bridge.offer)
for i, case in enumerate(cases):
    feed.begin_case(i, case)

# After the unchanged original 50 ms energy job has actually completed:
completion = completion_from_block(
    epoch=epoch, window=i, index=block_index, first=case['first'],
    total_samples=len(raw) // 2, stop=stop,
    rows=all_original_energy_rows_before_admission,
    available_s=elapsed_completion_time, producer_cpu_s=worker_cpu,
)
feed.submit(completion, elapsed_completion_time)
```

The callback is exactly `Bridge.offer(window, 'energy', epoch, rows, watermark,
done)`. `submit` returns the number of delivered completions. Logical cores,
600-sample halos, 50 ms blocks and the original conservative watermarks retain
their existing semantics. Candidates may lead a conservative coverage watermark;
the adapter retains them and lets the bridge wait. Complete empty blocks are
valid evidence of coverage. It never deduplicates or discards owned stock matches.
Only out-of-core halo copies are excluded by the helper.

Each `EnergyCompletion` includes RF epoch, window and sequence, exclusive RF
ownership `[start_tick, end_tick)`, observed RF frontier, watermark, actual causal
availability time, producer job identity/CPU receipt, all energy rows and the
terminal flag. Frames are copied into immutable owned storage so later producer
mutation cannot change queued evidence. Per-window sequences and ownership must
be contiguous and once-only; clocks and watermarks cannot regress. A terminal
receipt must close the exact registered core. Pending rows, completions, windows,
recent closed keys and the accounting ledger have explicit bounds. Overflow fails
closed; it does not silently shed packets or create timing evidence.

## Recorded replay

`SharedEnergyFeed(..., replay=True)` additionally allows
`queue_replay(completion)` and `release(now_s)`. Future completions remain
quarantined until their recorded completion/receipt time. Do not substitute RF
block end, synthetic timing, or the point at which a replay happened to read a
file. Ordinary `submit` rejects a future completion. In both modes, the RF
frontier and ownership must cover every candidate and declared watermark.

The available eight-second fixture has no original per-method producer completion
timestamps. A valid engineering test can measure the unchanged full energy
producer on that RF, retain its whole unfiltered candidate output and its measured
availability times, then replay that trace as an explicitly isolated producer
measurement. This is not observed live production sharing or live latency.

## CPU accounting

`EnergyAccounting` can be shared by several adapters. It deduplicates upstream CPU
receipts by producer job identity, rejecting conflicting receipts. `summary(8)`
reports upstream CPU counted **once**, measured adapter CPU and the scope limit.
Downstream native decoder/admission/relay CPU must be added to that total. Do not
compare consumer-only CPU with a baseline containing the energy producer: that
would hide roughly 0.162 CPU seconds/RF second from the preceding Pi result.

The adapter performs zero duplicate energy decodes; that alone does not prove a
measured saving. A fresh producer measured once and fanned out to consumers is
shared compute. A separately recomputed duplicate baseline must be measured and
reported as such. If the current pipeline already computed energy once, there is
no second producer cost to subtract from its existing CPU total.

## Checks

Run `python3 shared_energy_tests.py`. Thirteen standalone tests cover causal
availability, replay quarantine, callback semantics, immutable ownership, epoch/
sequence/gap/overlap rejection, extras-only rejection, conservative watermarks,
missing/future RF, clock regressions, RAM bounds, empty blocks, shared CPU receipts
and exact original core/halo ownership across all 21 blocks of one RF second.
No RF or receiver access is required.

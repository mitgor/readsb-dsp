# Incremental native Stream1090: admission and test-relay validation

10 November 2026, Europe/Berlin. **Isolated historical RF replay; nothing deployed.**
Hardware: Raspberry Pi 5 Model B Rev 1.0.

The 20 ms decoder now has a test admission bridge and one shared Rust final
transmission history. Energy runs independently in 50 ms blocks. Original stock
arrivals are replayed causally; final output reaches an anonymous RAM-only socket
sink, never a feeder. The original one-second logical reset remains intact.

## Retention and latency

Pi batch extras: **79**; retained with incremental
publication: **79**; losses: **0**;
new transmissions relative to this batch baseline: **0**.
Both modes have exact raw native packet/timestamp/order parity and identical raw
energy outputs. Raw native and energy outputs also match exactly between Mac
and Pi; all 79 Pi admitted packet timestamps match the batch condition exactly.
All 6630 captured stock DF17 frames
are byte/order preserved through the sink, with identical stock SHA-256 in both
modes. Other stock frame types were not retained in this fixture.

Latencies below are from the estimated RF packet end to **test-socket receipt**.
They include producer, stock/energy admission and shared deduplication time.
They exclude real live tap scheduling and FR24 processing/network/cloud latency.

| Platform | Native mode | Output | Extras | Early / fallback | Median ms | p95 ms | Max ms | <=250 ms |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Mac | batch | stream1090 | 47 | 0 / 47 | 400.0 | 873.2 | 1017.3 | 16 |
| Mac | batch | energy | 32 | 0 / 32 | 588.9 | 901.4 | 963.7 | 9 |
| Mac | batch | all | 79 | 0 / 79 | 476.9 | 914.9 | 1017.3 | 25 |
| Mac | 20ms | stream1090 | 47 | 46 / 1 | 49.1 | 86.6 | 975.4 | 46 |
| Mac | 20ms | energy | 32 | 32 / 0 | 55.8 | 77.6 | 164.5 | 32 |
| Mac | 20ms | all | 79 | 78 / 1 | 52.1 | 86.6 | 975.4 | 78 |
| Pi | batch | stream1090 | 47 | 0 / 47 | 1035.0 | 1582.0 | 1753.6 | 0 |
| Pi | batch | energy | 32 | 0 / 32 | 1204.8 | 1454.3 | 1720.5 | 0 |
| Pi | batch | all | 79 | 0 / 79 | 1078.9 | 1582.0 | 1753.6 | 0 |
| Pi | 20ms | stream1090 | 47 | 46 / 1 | 740.7 | 1060.5 | 1136.3 | 10 |
| Pi | 20ms | energy | 32 | 32 / 0 | 722.0 | 1093.1 | 1171.1 | 9 |
| Pi | 20ms | all | 79 | 78 / 1 | 732.3 | 1093.1 | 1171.1 | 19 |

A finalization fallback reuses cached raw rows when early clock/energy evidence is
insufficient; it does not re-decode RF or bypass stock guards. Its slowest packet
is included above. The fixture lacks original 20 ms RF-arrival timestamps. The
+50 ms clock-sensitivity counts are in summary.json; 50 ms is a sensitivity test,
not a proven physical error bound. These are not live antenna-to-feeder results.

## CPU

CPU seconds per RF second; **total is the whole isolated two-method process**,
including admission, stock replay and sink. Worker columns use thread CPU clocks.
Imports, controls and deferred post-measurement references are excluded. This is
not the CPU consumption of the complete live DSP pipeline. There is one paced
run per condition, not a balanced repeated CPU study. The Mac native and energy
worker costs vary substantially between conditions, so its CPU percentage is
sensitive to scheduling/DVFS and must not be treated as a portable overhead.

| Platform | Native mode | Total CPU s/RF s | Native | Energy | Admission main |
|---|---|---:|---:|---:|---:|
| Mac | batch | 0.1059 | 0.0497 | 0.0409 | 0.0048 |
| Mac | 20ms | 0.2755 | 0.1061 | 0.0921 | 0.0416 |
| Pi | batch | 0.3366 | 0.1099 | 0.1715 | 0.0310 |
| Pi | 20ms | 0.3704 | 0.1165 | 0.1622 | 0.0686 |

Mac: incremental total process CPU change **+160.2%**.
Pi: incremental total process CPU change **+10.0%**.

Pi was nice19 on core3 with a quota of 35% of **one** core. A 1 GiB memory limit
was requested, but the host exposes no memory controller; it was **not enforced**.
Measured peak RSS was 211.8 MiB.

The incremental subset needs about **37% of one core** for sustained RF, slightly
more than the imposed 35% quota. Queuing therefore remains: only 19 of 79
extras were under 250 ms on Pi. Zero losses on this short replay does not
establish sustainable real-time throughput. The Mac result must not be
presented as achieved Pi latency.

## Distance and complete recorded-pipeline comparison

The two-method union contains energy plus Stream1090 extras over stock. Some of
these are also recovered by other DSP methods. “Beyond other DSP” removes the
recorded full producer set excluding Stream1090; it must not be added twice to
the complete-pipeline count. There are no new transmissions beyond the recorded
complete pipeline or actual relay in this fixture. This work reduces delay,
not the decoder's recovery threshold.

| Range nm | Energy | Stream1090 | Union | Beyond recorded other DSP |
|---|---:|---:|---:|---:|
| 0–50 | 3 | 4 | 7 | 3 |
| 50–100 | 10 | 27 | 37 | 11 |
| 100–150 | 14 | 8 | 22 | 5 |
| 150–180 | 2 | 4 | 6 | 1 |
| 180–200 | 0 | 1 | 1 | 0 |
| 200–250 | 0 | 0 | 0 | 0 |
| 250+ | 0 | 0 | 0 | 0 |
| unknown | 3 | 3 | 6 | 2 |

Ranges use causal stock positions only, NIC/NACp>=5, age<=15 seconds and no
MLAT/TIS-B. They are not independent truth. The lone >=180 nm packet is inadequate
for a range-performance claim. Six unknown-range packets remain unknown.

The recorded full producer journal has 210
events, including 22 Stream1090 first-winner extras, and the actual relay reference
has 7950 DF17 frames. Other methods' completion
times are absent: this is **not a timed replay of the full current pipeline**.
The eight RF seconds are reserved historical engineering data, not fresh
prospective validation or training labels.

## Controls and live state

Twelve synthetic admission/dedup/socket controls passed on Mac and Pi. The previous
incremental study's boundary, split, deadline, overflow, noise, exact-packet and
sanitizer checks remain applicable: the native incremental decoder was unchanged.
Original-first stock identity/conflict guards, CRC and alignment requirements
were retained. Late stock always passes and its duplicate race is counted.
Protected PIDs/configuration/methods/gain/cap and primary sample-loss counters
unchanged during the completed target run: **True**. No receiver, feeder,
relay or collector restart, routing change, archive deletion or flush occurred.
The RF cap remains 5,000,000,000 bytes.

**Separate pre-existing live event:** the native rollback guard restored the
executable at 16:37:15 UTC, before this admission experiment, after a primary
sample-loss counter increase. The isolated reference is the previously validated
native batch library. The guard trigger does not establish causation. This task
leaves the executable fallback unchanged. FR24 and collection remain connected.

The initial complete Pi prototype lost 13 of the 48 transmissions emitted by
its also-overloaded batch condition; 31 of the 79 deferred-reference extras were
already rejected by that initial batch condition. Cached watermark scanning alone
then retained 74/79. These failed gates are preserved with their exact source
copies. Candidate-specific indexes reduced incremental CPU from 0.6191 to
0.3704 CPU seconds per RF second (about 40%), retaining 79/79. No age threshold,
CRC guard, decoder rule or clock tolerance was relaxed. A separate Mac audit
required the narrowed and original full-index admission functions to return
identical outputs, alignment audits and counters for every slice.

Two setup attempts stopped before RF replay: macOS transfer metadata was treated
as a source filename; then preflight found that the expected live native library
had already been removed by rollback. Both failures are preserved privately.
The completed target runs verify the pinned native baseline and actual
unchanged executable configuration explicitly.

## Next gate

Keep this experimental. First remove remaining Python admission/copy overhead
and reuse the existing production energy frontend instead of duplicating it.
The current result is not a sub-250 ms Pi deployment candidate under this quota.
Before a production admission/publication change, validate on longer untouched
RF with adequate distant opportunities, real tap-arrival timestamps and
all-method completion journals. Review the rollback's sample-loss
event separately before considering another native activation.

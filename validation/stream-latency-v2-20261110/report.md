# Four-part Stream1090 latency optimization

10 November 2026, Europe/Berlin. **Implemented by four subagents, integrated and
tested on Mac and Raspberry Pi 5 Model B Rev 1.0. Production unchanged.**

The new path shares complete upstream energy candidates, uses persistent Rust
stock/admission indexes, wakes on actual producer completion and retries pending
cold-start slices when new causal evidence arrives. The same 20 ms native decoder,
50 ms energy algorithm, trust resets, CRC/identity/conflict/alignment checks and
shared five-second Rust final transmission history remain in place.

The paired Pi medians improved from 957/571 ms to 189/151 ms, retaining 79/79
transmissions in each trial. **The sub-250 ms tail target is not consistently met:**
optimized p95 was 488 ms and 250 ms, with 52/79 and 75/79 packets under 250 ms.
There is very little margin beneath the 35%-of-one-core quota; supervisor health
monitoring also consumes CPU outside the measured benchmark child. This is a
promising isolated implementation, not a proven production latency guarantee.

## Paired retention and latency

Two trials reverse condition order. Each condition replays the same eight reserved
RF seconds with actual recorded stock arrivals; no future stock or incomplete
producer journal authorizes candidates. Both optimized trials retained the
baseline transmissions: 79/79 retained, zero lost and zero new relative to
that baseline in each trial.

| Host | Trial | Mode | Extras | Early/fallback | Median ms | p95 ms | Max ms | <=250 ms |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Mac | 1 | legacy | 79 | 78/1 | 51.8 | 87.1 | 973.6 | 78/79 |
| Mac | 1 | optimized | 79 | 79/0 | 52.7 | 83.9 | 221.0 | 79/79 |
| Mac | 2 | optimized | 79 | 79/0 | 51.3 | 79.5 | 224.4 | 79/79 |
| Mac | 2 | legacy | 79 | 78/1 | 51.6 | 91.2 | 979.2 | 78/79 |
| Pi | 1 | legacy | 79 | 78/1 | 957.3 | 1558.4 | 1591.7 | 12/79 |
| Pi | 1 | optimized | 79 | 79/0 | 188.5 | 488.5 | 537.5 | 52/79 |
| Pi | 2 | optimized | 79 | 79/0 | 151.3 | 249.6 | 269.4 | 75/79 |
| Pi | 2 | legacy | 79 | 78/1 | 570.7 | 953.8 | 1042.0 | 22/79 |

These are estimated RF-packet-end to **anonymous test-socket receipt** latencies.
Original 20 ms tap-arrival timestamps are missing. They are not measured live
antenna/USB-to-FR24 latency. The +50 ms sensitivity counts remain in summary.json;
50 ms is not a proven bound on clock error. The tiny RF sample is an engineering
regression, not fresh prospective or sustained-load proof.

Optimized Pi publication by method:

| Trial | Source | Extras | Early/fallback | Median ms | p95 ms | <=250 ms |
|---:|---|---:|---:|---:|---:|---:|
| 1 | energy | 32 | 32/0 | 188.8 | 443.4 | 19/32 |
| 2 | energy | 32 | 32/0 | 127.9 | 258.2 | 29/32 |
| 1 | stream1090 | 47 | 47/0 | 186.9 | 488.5 | 33/47 |
| 2 | stream1090 | 47 | 47/0 | 151.3 | 246.5 | 46/47 |

## CPU and honest shared-compute accounting

**All upstream energy computation is included once in each measured total.**
The sharing adapter performs no RF decoding; it receives full pre-admission
energy completions from the unchanged test producer. Consumer CPU is total minus
that upstream energy thread's CPU; it is a subtotal, not the complete system cost.
The benchmark does not connect to the live production publisher or measure a
full-system saving from eliminating an actually running duplicate producer.

| Host | Trial | Mode | Total CPU s/RF s | Native | Upstream energy | Admission main | Consumer subtotal |
|---|---:|---|---:|---:|---:|---:|---:|
| Mac | 1 | legacy | 0.2767 | 0.1060 | 0.0939 | 0.0417 | 0.1828 |
| Mac | 1 | optimized | 0.2709 | 0.1094 | 0.0988 | 0.0217 | 0.1721 |
| Mac | 2 | optimized | 0.2636 | 0.1079 | 0.0971 | 0.0238 | 0.1666 |
| Mac | 2 | legacy | 0.2685 | 0.1041 | 0.0910 | 0.0405 | 0.1775 |
| Pi | 1 | legacy | 0.3864 | 0.1160 | 0.1715 | 0.0747 | 0.2149 |
| Pi | 1 | optimized | 0.3478 | 0.1150 | 0.1591 | 0.0368 | 0.1887 |
| Pi | 2 | optimized | 0.3411 | 0.1147 | 0.1587 | 0.0352 | 0.1823 |
| Pi | 2 | legacy | 0.3615 | 0.1151 | 0.1609 | 0.0635 | 0.2006 |

Pi average total: **0.3740 -> 0.3444 CPU seconds per RF second**
(**-7.9%**). Admission-main excludes stock-index insertion and other loop
work, which remain included in total. Warmup, import/build/tests and deferred
post-measurement reference replay are excluded. The earlier wrapper microbenchmark
found 54–62% less evaluate CPU and 85–88% less marshalling CPU after bounded
immutable row caching/bulk input copies; those percentages are **not** full-pipeline
CPU reductions. Only two paired trials were run; scheduling/DVFS variation remains.

The job was nice 19/core 3, quota 35% of one core, finite 600 seconds, MemoryMax1G
requested and zero swap. The host exposes no memory controller, so the memory
limit was **not enforced**. Peak measured process RSS: 211.3 MiB.
CPU seconds/RF second describe workload demand, not instantaneous quota usage.

## Distance and complete-pipeline overlap

| Range nm | Energy | Stream1090 | Union beyond stock | Beyond recorded other DSP |
|---|---:|---:|---:|---:|
| 0–50 | 3 | 4 | 7 | 3 |
| 50–100 | 10 | 27 | 37 | 11 |
| 100–150 | 14 | 8 | 22 | 5 |
| 150–180 | 2 | 4 | 6 | 1 |
| 180–200 | 0 | 1 | 1 | 0 |
| 200–250 | 0 | 0 | 0 | 0 |
| 250+ | 0 | 0 | 0 | 0 |
| unknown | 3 | 3 | 6 | 2 |

Ranges use recorded causal stock positions, NIC/NACp>=5, age<=15 seconds, no
MLAT/TIS-B. Unknown stays unknown. There is only one known >=180 nm recovered
packet, inadequate for any range-improvement claim. The 22 transmissions beyond
recorded *other* DSP are existing Stream1090 recovery, not new extras introduced
by this optimization. No new packet appears beyond the recorded complete
pipeline or actual relay. Missing per-method completion times prevent a timed
replay of all current DSP methods; their journals are post-measurement masks only.

## Validation and limits

Native admission passed 333 exact Python/Rust comparisons across 14 control groups,
including 176 historical actual-RF energy/deferred all-source checks. Sharing has 13
controls, completion bridge 22 Python/native controls and cold retry 14 controls.
Tests cover future-evidence rejection, bounds/epochs, CRC/identity/conflicts,
quarter ticks, source priorities, stock eviction, stale cache evidence, idle drains,
pending retries and final fallback. The incremental decoder itself was unchanged;
its earlier boundary/deadline/noise/sanitizer regressions still apply.

Raw native and energy outputs match exactly between Mac and Pi in all trials;
original stock bytes and order are preserved. Detailed parity checks are in
summary.json.
All packet payloads and raw decoder timestamps match. In the admitted Pi output,
10 of 158 paired timestamps differ by one 12 MHz tick (83 ns) because clock
calibration uses earlier causal evidence. The remaining 148 match exactly. All
transmissions remain matched within the unchanged 120 us tolerance.
Original stock DF17 bytes/order are preserved in every condition. The fixture did
not retain all other stock message types. All candidate outputs remain quarantined
and are never training labels or feeder input. No receiver/feeder/relay/collection
service was restarted. Models/gain/routes/switches and the 5,000,000,000-byte RF cap
are unchanged. Protected target state unchanged: **True**.

An initial harness erroneously tested NativeAdmission truthiness by its empty
stock length, selecting the legacy bridge. That Mac result is preserved as
invalid for the optimized condition. An explicit engine/bridge assertion now
prevents this; the setup-only Pi unit was stopped before RF replay, with source
and logs retained. Final results use all four components, including shared input
accounting and completion/retry counters, verified explicitly.

The live native guard had already restored the executable at 16:37 UTC before this
work after a primary sample-loss counter increase. This experiment leaves that
fallback intact; it neither reactivates native inference nor attributes that
older counter event to a particular cause.

## Deployment gate

Nothing was deployed. Judge latency using the actual Pi rows above, not the Mac
result. Before enabling this path, collect longer untouched RF with actual tap
arrival/completion times and adequate distant opportunities, validate sustained
queues/retention against the complete enabled pipeline, and retain the existing
fallback. Component correctness and a short engineering replay do not establish
production latency or range performance.

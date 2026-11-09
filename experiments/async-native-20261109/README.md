# Native-speed Pi comparison — 9 November 2026

SIC is off **in the test copies only**. Production settings, models, sources,
readsb/FR24/relay/DSP/collector services, gain and RF cap remain unchanged.

Three conditions on identical reserved 16 RF windows, each twice:

- synchronous with SIC: full current-method reference;
- synchronous without SIC: isolates the deliberate SIC tradeoff;
- asynchronous without SIC: isolates transport/admission overhead and timing.

Input RF clock is 1×. The finite root-owned executable tmpfs copy uses the current
hash-verified production Rust/native libraries and models, two DSP workers on 2/3
and coherent workers on 0/1, nice 19, CPUWeight 10, a 200% Linux CPU ceiling across four
allowed cores,1GiB and bounded runtime. This allowance replaces the earlier 35%
quota/12× slow-clock setup, only for authorized native-speed testing. No mount,
network/access policy or permanent service configuration changes are made.

`benchmark.py` runs actual native algorithms and encoded test-only output. Sync
mode follows unchanged whole-group comparison, then Stream1090, then 3 s ordered
relay. Async mode uses independent futures/Stream1090 and one shared 5 s / 120 µs
history. Both retain full original grouping for baseline audits. Stock context
is captured valid DF17, not the entire live ModeS/control stream. Post-run reference
audits and initialization/warmup are outside timed CPU; worker/Stream1090/parent
CPU are measured separately. Frame/byte matching, deliberate SIC losses and
transport losses are distinct.

`completion.py` fixes a real race discovered at native speed: a future can finish
and be removed by normal grouping during the pop call. Keeping pre-pop references
and collecting before and after avoids missing its result, without waiting for
unrelated slow futures. Raw seam events are never pre-deduplicated. Tests cover
this consumed-future race and ready-versus-pending publication on both Mac and Pi.

`protected.py` monitors current production hashes/PIDs/config, gain, radio sample
loss and feeder health, and proactively aborts only the owned child if live DSP
approaches 2.3 s. It never repairs or restarts production. A brief FR24 disconnect
interrupted the repeated sequence; completed conditions were retained and the
remaining three were repeated after reconnect. No production PID/config change.

`prepare.py` uploads a new owned fixture/runtime. `protected.py` defaults to the
six-condition order; --modes can explicitly resume remaining conditions into a
new output directory. Do not overwrite old attempts. Root executable-tmpfs paths
avoid the /run noexec and pi-owned semaphore cleanup issues from earlier work.
`fetch.py` copies/verifies closed results and failed histories. `analyze.py`
reports paired averages, source/time limits and only redacted aggregates.

The first constrained test and grouping-assertion failure are preserved but not
pooled with completed conditions. The SIC-on low-priority control copies missed
57/148 output deadlines under contention. This is not evidence of those losses
in the higher-priority working pipeline. Both SIC-off conditions retained all 319
matching-method extras in both repeats, with 0 duplicates. The frozen SIC-on
reference has 320; the deliberate one-packet loss is at about 50 nm.

The 16 RF windows are reused engineering/evaluation-only data with a known excluded
copy gap. No qualified >=180 nm extra opportunity exists here. No model/threshold
fitting, distant-range claim, RF-to-cloud latency measurement, wattage claim or
production activation is part of this task. See validation/async-native-20261109.

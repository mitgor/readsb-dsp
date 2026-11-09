# Stream1090 Rust shift-register/CRC experiment — November 9, 2026

User authorized an isolated Rust port and Pi comparison of whichever of sequence,
pulse discriminant and Stream1090 currently costs most. Production must remain
unchanged. No installation, model/method/routing change, service restart, SDR or
mirror access, packet injection, recorder flush or persistent archive deletion.

A simultaneous 60-second live CPU delta selected Stream1090: 12.35% of one core,
versus sequence 11.09% and pulse 1.71%. These are exclusive attributed costs;
shared frontend overhead is separate. This is not a causal marginal-cost or
energy measurement. Device is the current Pi 5 / Cortex-A76, not a Pi 4.

This ports Stream1090's eight-stream per-bit `ShiftRegisters::shiftInNewBits`
recurrence to Rust, not its entire C++ decoder. Both 56-/112-bit CRC state,
128-bit shifted frame state and handled-downlink mask are preserved. ARM NEON
operates four streams per group. All other stream demodulation, interpolation,
filtering, address trust, repair, duplicate handling, packet output and sample
clock behavior stay in unchanged C++. Other preset widths fall back to C++.
Derived code is GPL-3.0-or-later, retaining upstream attribution. Source snapshot:
Stream1090 commit 2189bdaca1d62d5e88600b21a281ccc5c18012f2.

## Reproduction and evidence

- `stage.py` uploads the exact receiver binary, source snapshot, frozen 24-second
  historical RF corpus and checksum-verified temporary Rust 1.99.1 compiler into
  owned tmpfs. Private raw inputs/results live in the adsb-neural-rescue workspace.
- `build.py` builds C++, Rust and an optional attribution-only gprof variant. The
  target control/candidate compile only the production-selected 2.4/8 MHz preset,
  using the actual C++ flags (`-O3 -ffast-math -mcpu=cortex-a76`). No fast math is
  used in Rust's exact integer recurrence. Actual production ELF is a third
  output/timing reference, guarding against rebuild/preset-layout effects.
- `state_test.cpp` checks 1.2 million full-state updates on zero/one/alternating/
  random bits and seeded register extremes. A separately compiled, ABI-matched
  C++ kernel prevents cross-call optimization and discarded CRC work from
  invalidating the kernel microbenchmark. That microbenchmark includes identical
  deterministic bit-generation overhead. Full decoder timing includes FFI costs.
- `benchmark.py` requires byte-for-byte complete AVR stdout parity for every RF
  second and negative control (including payload, timestamp, RSSI and order).
  Five counterbalanced rebuilt-C++/Rust trials measure precise child CPU. Noise,
  DC and clipping controls must match the actual binary. Separate `memory.c` exec/fork launcher
  samples measure decoder RSS: Linux wait4 launch RSS may include Python's spawn
  image, so raw launch high-water is retained but not presented as decoder RAM.
- `timing.py` adds seven counterbalanced actual-production/C++-control/Rust trials
  on identical RF and verifies exact output hashes on every invocation.
- `run_pi*.py` supervisors check protected service PIDs, model/library/config
  hashes, gain, methods, sample loss, feeder/collector health and processing
  margin every three seconds. All tests run nice19/core3/CPUQuota35%, finite
  runtime and a conservative summed-child RSS ceiling below 1 GiB. MemoryMax1G
  was requested; this kernel lacks a usable memory controller, so independent
  RSS monitoring provides the effective bound. Only an owned child can abort.
- `fetch.py` checksum-verifies/fsyncs the complete closed target bundle on Mac.
  `cleanup.py` rechecks every exact owned file/symlink identity before removing
  only that tmpfs tree. No persistent receiver archives are touched.

Early scalar and NEON development trials are preserved separately. Rust `const
fn` alone did not force polynomial-delta evaluation at compile time; assembly
inspection exposed repeated fixed loops. The final port uses explicit `const`
deltas. Initial all-presets compilation was stopped to bound compile cost; an
early target launcher ran before an upload completed and performed no test.
These logs and corrected harness build errors are preserved, not final results.
The first final run completed parity/timing but found no `/usr/bin/time` for RSS;
`pi_complete.sh` repeats complete checks using a tiny C RSS launcher instead,
without installing packages. Its protected-complete record gates the final result.
No model or decoder decision thresholds were fitted to the evaluation RF.

The corpus has ten >=180 nm stock opportunities from three aircraft and only one
Stream-only distant extra in its existing full-pipeline comparison. This tests
regression parity, not prospective range improvement. Raw exact-output equality
preserves its 34 Stream-only additions and 403 full-union extras, with no added or
lost packets. Previous Rust coherent/acquisition replay parity connects that
frozen comparison to current production kernels; no new training labels result.

The optional gprof build forces the shift update out of line and enables `-pg`;
its attribution is diagnostic only. Never use its time for speed claims or assume
its percentages equal the optimized inlined production instruction profile.

Reports use dated destinations and do not overwrite earlier experiments. Read the
current state before re-running any launcher. No candidate activation is included.

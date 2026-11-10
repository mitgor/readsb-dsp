# Rust pulse-discriminant port — November 10, 2026

User requested porting the C pulse filter to Rust, validation and production
activation. This directory contains isolated validation; deployment/rollback is
in experiments/pulse-rust-activation-20261110.

`pulse.rs` ports both scalar eight-tap discriminant and the experimental 1–8-model
bank. FP64 accumulation order, FP32 logits/confidences, scale floor, normalization,
finite/nonnegative checks, error return codes and partially written output on
invalid late input match C. Model, candidate selection, bounded workload and
header/address/CRC repair/admission rules are unchanged. No new bank is enabled.

`prepare.py` collects the first 160 historical pulse-policy candidates per RF
second across 24 already-consumed RF seconds. It preserves the exact 482-sample
power neighborhood and frozen model. No current SDR/mirror access or labels.
`build.py` builds O3/no-FP-contraction C and O3 Rust (no fast math); target tests
also use the exact live C ELF. Rebuilt C and actual C hashes are identical.

`benchmark.py` checks all logits/confidences bit-exactly on 3,840 recorded windows,
58 numerical/error/bounds/partial-write cases, and six bank/model-count controls.
It includes zero/subnormal/large power, overflow, invalid preamble and early/late
bit neighborhoods, random weights/bias and unchanged weak-bit CRC packet logic.
Nine counterbalanced trials with 50 calls per mode measure batch CPU on Pi.
Bank results also match independent scalar calls. Packet-window outputs are not
new unique extra transmissions beyond the production pipeline.

Target kernel CPU is ~6% higher than actual C (~5.35% versus C paired trials),
not a speedup. Mac was roughly neutral. The user requested Rust deployment, not
a CPU-saving gate; activation is conditional on parity, protected health and
processing margin. No full-system/energy improvement is claimed.

`stage.py` copies current sources, all models and actual libraries, including
already active Rust sequence/coherent/acquisition plus existing neural/DSP paths.
Only the isolated candidate pulse ELF is replaced. Full 24-second native ring
replay matches every raw/guarded packet, alignment audit and admission decision.
SIC/header remain off; broad CRC stays quarantined. Stream child remains separate
and unchanged; its previously identical RF output preserves the complete union.

All measured Pi work is nice19/core3/CPUQuota35%, finite runtime, requested
MemoryMax1G and independent conservative summed-child RSS monitoring below 1GiB
(the kernel lacks an effective memory controller). The supervisor checks protected
service PIDs, sources/libraries/models/config/Stream ELF hashes, gain, methods,
SDR loss, collector/FR24 health and production processing margin every three
seconds. Only the owned benchmark may abort. No service restart, config/model
change, packet injection, recorder flush or persistent archive deletion in tests.

`finalize.py` verifies closed-run parity/health and preserves a hash-verified
candidate for deployment. An early finalization call was refused while the
benchmark was still closing; no gate was bypassed and no deployment occurred.
`fetch.py` streams the full source/compiler/model/RF/library/result/log bundle to
Mac, verifies every SHA-256 and fsyncs it. `cleanup.py` rechecks exact identities
before deleting only the closed owned tmpfs tree. Reports publish aggregates only.

This is regression RF, not fresh prospective evidence: only ten >=180nm stock
opportunities from three aircraft. No range-improvement or training-label claim.
Dated scripts/paths are frozen records; inspect current state before reusing.

# Native Stream1090 repair/trust comparison — 2026-11-10

This experiment tests `readsb/contrib/stream1090-native`, an optional in-process
C++20 extension of the native clean-CRC algorithm port. It reuses the deployed
Stream1090 core, not a subprocess. It does not enable or link itself into live
readsb or any feeder. See [results](../../validation/stream-repair-20261110/report.md).

## Reproduction

Use the existing project Python with numpy for synthetic controls and stdlib
for the benchmark. All scripts take explicit input/output paths and refuse to
overwrite result files. The private run root contains `prepared/rf.bin`,
`cases.json`, `references.json`, `positions.json`, `other-dsp-accepted.json` and
checksum-backed source/input manifests from the prior native comparison. The
119 long RF seconds and 383 recent clips are reserved historical evaluation
RF, never training labels. Do not describe them as fresh prospective validation.

Build a native benchmark library with C++20/O3/fast-math, the source directory
on the include path and `-fPIC`. Compile `native.cpp` to an object with
fast-math; compile `phase_wrap.cpp` separately and link both objects with
`-shared` WITHOUT fast-math, avoiding a load-time floating-point-mode change.
`fenv_load.cpp` checks that loading the final library preserves that mode.
For parity with the measured Pi build use `-mcpu=cortex-a76` and the upstream
macros recorded in `protected_pi.py`. Do not overwrite a production library.

Run `benchmark.py --root ROOT --native COPIED_LIBRARY --binary COPIED_EXECUTABLE
--output NEW_RESULT --repeat N`, then `attribution.py --root ROOT --result
NEW_RESULT --output NEW_ATTRIBUTION`. Physical core boundaries use the frozen
original-C measured stock-to-RF offset of 2,400 ticks. Native/executable clock
alignment is calibrated independently; their 769-tick output offset must not
replace the physical RF origin. Initial results using that incorrect boundary
origin are preserved privately as `initial-coordinate-audit`, excluded from
final performance tables. No inference algorithm or acceptance threshold was
changed when correcting the harness.

The final safe-link build has one paired Pi pass. Earlier multi-pass coordinate
audits and the intentionally stopped direct-link run are retained privately;
none are mixed into final performance statistics. No protected service was
interrupted by either harness correction.

`repair_controls.py` tests known trusted/untrusted synthetic bit repairs against
the executable; `controls.py` tests clean packets and noise. `api_sanitize.cpp`
and `trust_solver_unit.cpp` check API fail-closed behavior, direct non-table
erasure solving, trust separation and expiry under ASan/UBSan on Mac.

`protected_pi.py` owns only the finite benchmark and its children. It uses
copied code and saved RF in an isolated owned tmpfs, monitors production health,
and stops only its own process group on sustained degradation. It does not
open the SDR, attach to a mirror, forward packets, restart services, force
capture flushes or alter the 5 GB RF cap. Nice19/core3/35% CPU quota and finite
900-second runtime were requested. Memory-controller enforcement is unavailable
on this target; do not claim the requested MemoryMax was enforced. Preserve and
checksum-verify/fsync Mac backups before cleaning owned tmpfs files.

`report.py --results PRIVATE_RESULTS --dest PUBLIC_REPORT` emits aggregates;
never publish private packet records, RF, configurations or receiver journals.

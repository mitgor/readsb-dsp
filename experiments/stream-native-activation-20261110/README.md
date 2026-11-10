# Extended native Stream1090 activation — 2026-11-10

Production adapter: `src/rescue/stream1090_method.py`, using the bounded C ABI in
`readsb/contrib/stream1090-native`. Existing one-second windows, CRC checks,
stock-clock calibration, prior-identity/conflict guards and cross-method
attribution are preserved. This does not enable incremental streaming.

`adapter_parity.py` compares complete output rows and alignment with an exact
copy of the deployed executable adapter/helper. The Mac gate used all 119
historical windows. The Pi gate used 34 windows: twelve uniform selections plus
all available distant-context cases from that same frozen evaluation corpus.
They remain reserved evaluation RF, never training labels. Deliberate native
timeout, invalid-checksum and repeated-failure controls must fall back to the
executable on the same input. `preflight_pi.py` runs only copied code/saved RF
under existing health checks, nice19/core3/35% quota and finite runtime.

`deploy.py` is installed as `/usr/local/sbin/adsb-stream1090-native-mode`.
It requires the existing deployment-health helper, captures exact rollback
files, checks archive room, installs the native library/adapter, and gracefully
restarts only `adsb-rescue-shadow`. Readsb, FR24, the relay, ADSBx and the RF
recorder are protected. Existing CRC RAM data is saved by normal graceful
shutdown. No collection archives or models are removed or changed.

`native-guard.service` and `native-guard.timer` provide independent persistent
rollback. Native failures first fall back inside the running adapter; two
consecutive health failures then restore the original adapter and persist
executable selection. A healthy coordinator need not restart for rollback.
A dead/stalled one restarts after restoration. Readiness has a separate deadline.
Reboot readiness is checked before rebasing process identities. Healthy guard
heartbeats live only in `/run`; persistent state writes occur for activation,
rollback, reboot and failure transitions. A feeder with no tracked aircraft is
not declared stalled solely for having no recent aircraft upload.

`rollback_unit.py` tests file restoration and two-strike behavior in a temporary
filesystem with all service operations mocked; it never interrupts production.
Do not test failure by corrupting a live library or opening another SDR consumer.
The final library is compiled with per-object optimization and linked without
fast-math, preserving the caller's floating-point mode on load.

The measured activation kept the recorder alive but its RF tap reported about
3.55 seconds of gap samples across the preflight/handover interval. Primary SDR
loss counters were unchanged. This is not evidence of a gapless mirror handover.

See [activation report](../../validation/stream-native-activation-20261110/report.md).
The private workspace retains checksum-backed candidate/rollback binaries,
preflight failures, live observations and manifests. Do not publish these raw
records, RF or credentials. Persistent rollback backups and guard units remain
on Pi; only verified owned tmpfs preflight files are cleaned.

# Rust Stream1090 activation — November 9–10, 2026

User authorized deploying the previously validated Rust Stream1090 kernel with
rollback while keeping FR24, readsb, DSP and collection running. Sequence Rust is
a separate offline experiment and is not part of this activation.

`install.py` verifies the durable prior target bundle, exact candidate ELF hash,
actual C++ ELF and all validated live sources/configs/models. It saves exact C++
rollback bytes/ownership/mode, then installs a dedicated guarded activation unit.
`control.py` atomically replaces only the existing Stream executable. The live
producer starts a fresh subprocess per RF second, allowing old in-flight work to
finish and the next job to exec Rust. No producer, receiver, feeder, relay, DSP
coordinator or collector restart, archive flush or persistent archive deletion.

The 300-second observation checks all protected PIDs (including DSP), models,
configuration, methods, workers, 38.6 dB gain and sample-loss counters; sustained
Stream RF/alignment progress, stock and Stream-extra forwarding; actual installed
inode execution through /proc. A persistent ten-second timer checks health,
queues, input/work/Stream progress, the processing margin and binary ownership.
Three repeated unsafe observations atomically restore the exact C++ ELF. Rollback
also requires no producer restart. An unexpected human binary change supersedes
this release instead of being overwritten. There is a systemd OnFailure fallback.

The existing coherent/acquisition guard retains its libraries and is never
stopped. This release reuses its snapshot/progress-policy helper at
/var/lib/adsb-rust-kernels-20261109; preserve that active dependency. Both helper
sources are included in the private activation evidence bundle.

`test_control.py` passes exact C++ restoration/no-restart and external-change
preservation tests locally. `save_evidence.py` preserves deployed control, units,
original/candidate binaries, helper sources, observations and journals in a
checksum-verified, fsynced private Mac archive. `report.py` exposes aggregates
only; no sharing keys, credentials, RF or model data are published.

Status:
`sudo python3 /var/lib/adsb-stream-rust-20261109/control.py status`

Manual rollback:
`sudo python3 /var/lib/adsb-stream-rust-20261109/control.py rollback`

Dated paths are frozen operational records. Inspect current live ownership before
reusing scripts. The finite observation passed; the persistent guard stays on.

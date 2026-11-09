# Rust kernel revalidation and coordinated production guard

Authorized 9 November 2026: investigate prior rollback; revalidate Rust coherent and acquisition on the Pi, then activate conditionally while protecting FR24 and data collection.

Read `validation/rust-revalidate-20261109/report.md` for findings and limits. All raw RF, model/source snapshots, journals and rollback binaries are preserved privately under the established adsb-neural-rescue workspace, not committed here.

Workflow performed:

1. `investigate.py` parses the preserved binary systemd journal and historical rollback evidence.
2. `stage.py` snapshots current protected configuration, models, actual production C libraries and exact preserved Rust releases into owned tmpfs.
3. `run_tests.py` and `full_replay.py` run kernel controls, alternating CPU measurements and six persistent full-pipeline replay cycles. `protected_health.py` supervises protected services, RSS and runtime.
4. `finalize_tests.py` asserts exact all-array/event parity, controls, source hashes and protected health. Saved proof gates installation.
5. `test_policy.py` and `test_restore.py` exercise progress classification, exact C restoration and human-change protection. Seven tests passed on Mac and Pi.
6. `install.py` installs only the three validated Rust libraries and the acquisition loader, saves exact previous bytes, and starts finite activation with a 300-second live observation. `control.py`/`policy.py` provide one persistent guard and rollback. Historical guards are retired without erasing their records. No feeder, receiver or collector restart.
7. `fetch.py` archives and checksum-verifies the complete closed test stage to durable Mac storage. `save_activation.py` separately preserves deployment backups, units, live observation and journals. `cleanup.py` removes only the exact unchanged owned test stage after receipt verification.
8. `report.py` creates a public redacted summary from private evidence. No raw RF or credentials are published.

Scripts have dated, fixed paths and are operational records, not a generic installer. Inspect current state before reuse; do not rerun activation blindly. Persistent guard runtime is `/var/lib/adsb-rust-kernels-20261109/control.py`; `status` reports ownership and `rollback` restores exact saved C bytes and restarts only the DSP coordinator. External changes supersede this release instead of being overwritten.

The target kernel lacks a usable memory controller: the benchmark requested MemoryMax=1G, and additionally enforced a conservative summed-process RSS ceiling below 1 GiB. Core 3, nice 19, 35% CPU quota and finite runtime were used. No SDR, mirror consumer, candidate injection, archive flush or persistent archive deletion was involved.

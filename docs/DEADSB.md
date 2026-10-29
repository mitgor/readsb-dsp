# Integration and rollback

Use a dedicated installation root and runtime for a manual migration. The package
has no command that replaces `/usr/bin/readsb` or automatically edits feeder
configuration. Preserve the existing installation and existing RF archives.

1. Build/test on Mac, then Linux target without opening the SDR.
2. Benchmark already-consumed RF; preserve frozen future evaluation reservations.
3. Run shadow-only rescue against the sole readsb I/Q tap. Its stock Beast input
   remains loopback port 30005; receiver ownership and sample timing stay readsb's.
4. Enable `--cpu-budget-config` explicitly. Coordinator status includes `cpu_budget`
   and per-job profile counters. Disabled/absent policy preserves the full bundle.
5. Validate sustained CPU, sample loss, stock packet/timestamp preservation,
   latency, temperature, method attribution and distant recovery before promotion.
6. Keep the established guarded relay to feeders. Native direct DSP output and
   the Python guarded relay have different validation histories; do not enable
   both DSP paths together or treat unverified native candidates as approved live
   extras. Broad CRC and research estimators remain quarantine-only.

A running governor reads the budget file every second. Dashboard policy writes
are atomic, schema-validated, same-origin and revision-checked, with no shell
commands or service control. Bind is loopback only. Reverse-proxy access requires
an explicit operator setup, separate from this package.

To disable admission control, set `enabled:false` in its JSON config. This restores
full configured work at the next RF-second boundary, without restarting stock or
feeders. To stop rescue completely, stop the dedicated rescue service; stock
readsb and its original Beast feed remain separate. Never launch a second SDR
reader as a rollback mechanism. Do not restart a recorder with unsaved RAM data
unless it has a verified save/backup path and space under its existing cap.

The project includes imported experimental modules so old offline benchmarks can
be reproduced; their presence does not enable them. Runtime configured methods
and the existing CRC/identity/duplicate/conflict acceptance gates remain decisive.
Production model hashes are checked by `rescue.model_cascade.production_paths`.

# Rust Stream1090 activation — November 9–10, 2026

Rust Stream1090's validated eight-stream shift-register/CRC kernel is active. The surrounding C++ decoder and guards remain unchanged. Previously measured median total Stream CPU reduction: 13.61% on the current Pi 5. No pulse-sequence Rust deployment is included.

The ELF was replaced atomically at the existing executable path. Each RF-second job starts a fresh process, so no receiver, DSP coordinator, relay, feeder, ADS-B Exchange or collector restart was necessary. The next spawned job used Rust; an already-running old job could finish normally.

The 300.2-second observation passed. 300 RF seconds were processed and 76 Stream extras forwarded while stock forwarding continued. 386 live process observations confirmed the installed candidate inode at the actual executable path. Forwarded extras show activity, not new recoveries versus C. All production PIDs, models, configuration, switches, 38.6 dB gain and sample-loss counters stayed unchanged. The RF cap remains 5,000,000,000 bytes.

One Stream-specific persistent timer checks receiver/feeder/collector health, input and worker progress, Stream errors/progress, queues, processing margin and binary ownership every ten seconds. Three repeated unsafe observations restore exact saved C++ bytes atomically. No producer restart is needed for rollback either. Unexpected human binary edits are preserved and supersede this release. The prior coherent/acquisition guard stays active and retains ownership of its libraries.

The activation has a systemd failure fallback and exact binary backup; two rollback tests passed (byte restoration without any service restart; preserving external human edits). Full live observations, original/candidate ELF, control and dependency sources, units, journals and checksum receipt are durably saved in the private results directory. No recorder flush or archive deletion occurred.

Status: `sudo python3 /var/lib/adsb-stream-rust-20261109/control.py status`

Manual rollback: `sudo python3 /var/lib/adsb-stream-rust-20261109/control.py rollback`

Finite live validation supports this activation; the persistent guard remains enabled. Public files contain no RF, credentials or sharing key.

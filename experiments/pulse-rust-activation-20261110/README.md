# Rust pulse production activation — November 10, 2026

Explicitly authorized after port/validation. `install.py` verifies the Pi parity
proof, candidate hash, exact live C reference and all protected source/model/
configuration fingerprints. Only `_pulse_discriminant.so` is replaced, at the
existing Python loader path; scalar and bank ABI remain compatible. No loader,
model, algorithm switch, gain or forwarding-policy change.

`control.py` saves exact C bytes/mode/ownership, checks ample clean shutdown-cache
headroom, and restarts only adsb-rescue-shadow to load Rust. Readsb, FR24, relay,
ADSBx and the RF collector stay running. Normal coordinator shutdown may save its
CRC RAM cache; no forced recorder flush or persistent archive deletion.

The five-minute live observation requires exact Rust inode mappings in both DSP
workers and a Rust backend marker; verifies existing sequence/coherent/acquisition
Rust mappings too; checks protected PIDs, gain/config/methods/worker settings,
Stream ELF, sample-loss counters, RF processing and stock/DSP/pulse forwarding.

A five-second persistent guard monitors ownership, mappings, completion/RF progress,
status age, queues, processing margin, temperature and receiver/relay/FR24/collector
health. Three repeated unsafe observations restore exact C and restart only DSP.
Unexpected human file edits supersede this release without overwrite. Systemd
provides activation-failure rollback and incomplete restorations are retried.

Checks/restores share the existing coherent/acquisition coordinator lock. During
initial observation this guard covers health while the coherent/acquisition and
sequence guards skip their nonblocking checks; they resume afterward. Stream
monitoring continues and performs no DSP restart. Keep the active shared helper
/var/lib/adsb-rust-kernels-20261109/control.py and policy.py; dependency sources
and the other release states are included in the evidence archive.

`test_control.py`: exact C restoration/coordinator-only restart and preservation
of human edits. `save_evidence.py`: deployed binaries, C backup, control, units,
helper sources, model/parity proof, observations and journals, checksum-verified
and fsynced on Mac. Reports contain aggregates, not raw RF or credentials.

Status: `sudo python3 /var/lib/adsb-pulse-rust-20261110/control.py status`

Rollback: `sudo python3 /var/lib/adsb-pulse-rust-20261110/control.py rollback`

The Rust batch cost is about 6% higher than the live C kernel. Deployment follows
the user's explicit request, with no CPU/energy/range improvement claim. The
finite live observation and ongoing rollback guard protect stability. Inspect
current ownership before rerunning dated operational scripts.

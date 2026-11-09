# Rust sequence production activation — November 10, 2026

User explicitly requested Rust sequence production after the benchmark. That
benchmark established exact output parity and ~20.5% lower batch CPU versus
optimized C, but only 0.48% complete-worker saving with an interval overlapping
zero. This activation makes no stronger performance claim.

`install.py` verifies the durable target archive and installs only the exact tested
Rust ELF and exact tested SequenceV3 loader overlay. The C `_pipeline_v3.so`
remains unchanged and supplies all other helpers. Existing Rust coherent,
acquisition, EM and Stream kernels, neural models, gain, methods and routing stay.

Exact old loader bytes, absent/new-library state, ownership and mode are backed up
before changes. `control.py` gates activation on normal-shutdown archive headroom;
it restarts only adsb-rescue-shadow, allowing stock/readsb/relay/FR24/ADSBx and the
RF collector to remain running. No forced recorder flush or archive deletion.
Normal clean coordinator shutdown may save its bounded CRC RAM cache.

Five minutes of observation verify both coherent workers map the exact Rust
sequence inode and return the expected backend marker; protected service PIDs,
configurations, gain, switches, worker configuration, Stream ELF and sample-loss
counters; sustained native/Stream RF, stock/extras and sequence forwarding. The
pulse model is independently verified against the parity-test source archive.

A persistent five-second guard checks queues, RF/completion progress, status,
processing margin, temperature, relay/FR24/collector health, exact file ownership
and actual Rust worker mappings. Repeated unsafe conditions restore the C loader
and prior library state, restarting only the DSP coordinator. Unexpected human
file changes supersede the release without being overwritten. Activation also has
a systemd failure fallback; incomplete restoration is retried.

All DSP restarts/checks take the existing coherent/acquisition guard's shared
coordinator lock. During the initial observation this controller covers health
while the older guard skips its nonblocking checks. On completion it resumes;
its timer, state, kernels and backups are unchanged. The Stream guard continues
throughout and does not restart the DSP coordinator. Preserve the active helper
dependency /var/lib/adsb-rust-kernels-20261109/control.py and policy.py; both are
archived in this activation evidence.

`test_control.py`: exact C loader restoration, new-library removal, coordinator-only
restart, and preserving unexpected human changes. `save_evidence.py` checksum-
verifies/fsyncs the deployed files, original rollback bytes, observations, units,
dependency sources and journals on the private Mac workspace. Reports are redacted.

Status:
`sudo python3 /var/lib/adsb-sequence-rust-20261110/control.py status`

Manual rollback:
`sudo python3 /var/lib/adsb-sequence-rust-20261110/control.py rollback`

Dated operational scripts are frozen records; inspect current ownership before
reuse. This is finite live validation with a persistent rollback guard, not a
lifetime stability, range, cloud-credit or energy-efficiency claim.

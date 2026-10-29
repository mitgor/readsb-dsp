# Rust defaults for acquisition and soft-phase EM

This release changes implementations, preserving method switches and routing.
The receiver's acquisition switch stays off. Soft-phase EM is an offline research
entrypoint, not an extra live feed stage. Installing its Rust backend does not
add EM packets to FR24. Ordinary/pair coherent remain on their existing Rust release.

`coherent_extended_opt.library()` prefers `_acquisition_rust.so`; equal-priority
peak fallback still uses the inherited SciPy policy. The complete
`_pipeline_extended_neon.so` stays intact for compatibility.
`research_science.decode(method='em')` prefers `_science_em_rust.so`; sequence
and combined modes retain `_science.so`. Removing optional Rust libraries uses C.
The direct low-level `research_science.library()` deliberately remains C because
its ABI supports all three methods.

Build in a disposable/output tree with Rust 1.99.1:

```sh
python tools/build_rust_methods.py --output /tmp/rust-methods-build
# Or explicitly select the optional bundle defaults:
python tools/build_bundle.py --native-only --coherent-backend rust --methods-backend rust
```

Default bundle builds remain C and remove previous optional method overrides.
Do not rebuild a working receiver in place; use the guarded activation instead.

The release checks compare scorer/candidate decisions against the actual receiver
C library, candidate-to-packet payload/start/repair signatures, noise and edge
controls, all EM arrays for 368 fixed windows at 1/2/4 iterations, and the Python
entrypoints including the C sequence modes. These are parity/regression tests,
not fresh reception or accuracy claims. Prior repeated performance benchmarks
are under `validation/rust-acquisition-20261029` and `validation/rust-phase-20261029`.
Release timing checks use three batches and are not a new robust speed ranking.

`tools/rust_methods_mode.py` requires the existing root-owned coherent health
helper. It backs up all changed files and records newly created files, restarts
only `adsb-rescue-shadow`, observes health and verifies unchanged protected PIDs,
configuration, gain, switches, sample loss and relay throughput. On failure it
restores previous files/removes additions and restarts only shadow. Its separate
systemd guard watches file hashes and live health every 15 seconds, rolling back
after three consecutive failures. A normal startup gets 30 seconds of grace.
Persistent rollback disables automatic reactivation.

```sh
sudo /usr/local/sbin/adsb-rust-methods-mode status
sudo /usr/local/sbin/adsb-rust-methods-mode rollback
```

The Pi staging area is owned `/dev/shm/rust-methods-main-20261029`; tests are
nice19/core3/35% CPU/1536 MiB/900 seconds and do not open the SDR or forward data.
Raw fixtures, compiler components and binaries remain private in `.work`.

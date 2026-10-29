# Live Rust coherent backend

The working Pi ordinary and pair-lag coherent decoders now use Rust. The shared
frontend, peak selector, energy/soft/timing/matched paths, neural models, packet
acceptance guards and feeder routing retain their existing implementations.
The C peak-selector tail is preserved byte-for-byte in `coherent_peaks.c` because
the existing Python wrapper expects that ABI export. It does not perform window
decoding. The Rust `rescue_coherent` entry point performs the full coherent math.

Production source is `src/rescue/coherent_rust.rs`. It adds the already enabled
pair-lag carrier branch to the validated ordinary port and preserves libc
sorting behavior for nonfinite quantile inputs. No unsafe unchecked indexing
is introduced in the decoder. A stable backend marker identifies each library.

## Build and verify

Rust 1.99.1 is the validated compiler. Nothing compiles on receiver startup.
The libraries contain their required Rust runtime and have no runtime dependency
on rustc/cargo or the temporary compiler directory.

```sh
python tools/build_coherent_rust.py --output /tmp/coherent-rust
# Or rebuild the checkout bundle explicitly with Rust coherent libraries:
deadsb build --native-only --coherent-backend rust
```

The bundle still defaults to C for installations that do not request Rust.
Neither command installs services or changes the active receiver. Python source
packages include the Rust source. The Rust builder exports the same existing
three entry points plus `rescue_coherent_backend`, and hides internal runtime
symbols to avoid cross-library symbol collisions. Debug sections are stripped.

`experiments/rust-live/validate.py` compares both actual installed C libraries
with release Rust libraries, using identical dlopen/C ABI drivers. It checks
3,269 saved development windows, 8,192 phase/amplitude augmentations per branch,
500 peak-selector cases per branch, unchanged input and basic ABI guard returns.
Pi output arrays match bit-for-bit, including floats; every packet, bit decision,
flag and repair must match. On Mac diagnostic floats use 1e-12 absolute tolerance
because complex arithmetic code generation produces tiny rounding differences;
no packet/decision tolerance is allowed. The initial tighter Apple floating
assertions exposed roundoff in confidence scores, not packet/decision changes.
These are regression checks, not fresh RF reception or false-positive claims.

Nine-trial earlier language comparisons remain under `rust-coherent/`. This
release is separately benchmarked (seven trials) against the currently installed
optimized C for both branches. It includes the production ABI and nonfinite
fallback. Run only on previously consumed RF and isolate Pi build/replay at
nice 19, core 3, 35% CPU quota and bounded memory/runtime. `pi_job.sh` uses the
same checksum-verified temporary compiler archives as the prior experiment.

## Cutover and persistent rollback

`tools/rust_coherent_mode.py` atomically installs only the two coherent libraries
and their new source files. It backs up the prior optimized C libraries and
file metadata. Only `adsb-rescue-shadow` restarts. Graceful shutdown saves its
CRC research cache with room checked against the existing archive cap. Readsb,
relay, FR24, ADS-B Exchange and independent RF capture keep their processes.
A brief pause in rescue work occurs during worker restart; stock feeding continues.

The activation observes 120 seconds, checks unchanged protected PIDs/configs,
gain/methods, sample counters, throughput, backlog, actual mapped library inodes,
FR24 uploads and stock/DSP/coherent forwarding. An activation exception restores
the backed-up C files. The transient systemd activation also has OnFailure wired
to the rollback unit, covering an unexpected activation process failure.

After activation the enabled `adsb-coherent-rust-guard.service` checks every
15 seconds. Three consecutive unhealthy checks restore the exact previous C
libraries and restart only shadow. Checks cover DSP/relay freshness, connectivity,
FR24 uploads, progress, worker bounds, temperature, sample loss, installed hashes
and library mappings. Repeated startup failures are detected separately. It
allows normal boot/worker startup grace and does not tie future health to old
PIDs, permitting ordinary reboot. A deliberate coherent method disable skips
mapping requirements. It does not measure or guarantee RF reception accuracy.

Guard health goes to root-owned `/run/adsb-coherent-rust/guard.json` (RAM), not a
continuous SD log. Persistent release/rollback state is root-owned under
`/var/lib/adsb-coherent-rust`. The guard exits after rollback and never silently
re-enables Rust. Other receiver settings and collection caps are never changed.

```sh
sudo /usr/local/sbin/adsb-coherent-rust-mode status
sudo /usr/local/sbin/adsb-coherent-rust-mode rollback
```

The explicit rollback is safe to repeat. Afterward the guard exits normally.
The old C sort-mode backup remains separately preserved. Unit fault-injection
tests (`test_guard.py`) check stale/stalled/loss/backlog/FR24 conditions, exactly
one rollback after three failures, and byte/mode-exact restoration without
restarting protected feeder/receiver services.

Deployment evidence: [Rust live report](../../validation/rust-live-20261029/report.md).

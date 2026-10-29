# Rust coherent decoding is live

Activated on 29 October 2026, with persistent automatic rollback to the previous optimized C libraries. Ordinary and pair-lag retry kernels use Rust; the existing C peak-selection helper and the rest of the DSP/neural pipeline retain their existing implementations.

## Release validation

| Target | Branch | Optimized C µs/window | Release Rust µs/window | Kernel CPU saving |
|---|---|---:|---:|---:|
| Mac M4 Max | ordinary | 6.281 | 5.640 | 10.2% |
| Mac M4 Max | pair-lag retry | 6.100 | 5.538 | 9.2% |
| Raspberry Pi 5 | ordinary | 19.469 | 17.338 | 10.9% |
| Raspberry Pi 5 | pair-lag retry | 18.569 | 16.646 | 10.4% |

Each release branch was compared against its actual installed C library with the same C ABI/dlopen driver and seven trials. The release includes safe Rust indexing, the nonfinite quantile fallback, the existing C peak selector and the production shared-library ABI. No fast-math or relaxed packet checks are enabled.

On Pi every output array matches bit-for-bit across 3,269 recorded windows, including floating diagnostics. Each branch also passes 8,192 augmented phase/amplitude windows with unchanged packets/repairs/hard decisions, 500 exact peak-selector cases and ABI guard checks. Thirty-two noise controls remain rejected. On Mac tiny floating confidence differences required a 1e-12 absolute diagnostic tolerance; packet bytes, repairs and hard decisions remain exact. Initial tighter Mac diagnostic assertions and their cause are documented in the experiment guide.

Both Rust branch unit tests pass, all 41 integration tests pass with Rust libraries built into the checkout, and seven watchdog/rollback fault-injection tests pass. Saved RF is already consumed development data. This is implementation regression, not fresh reception validation or a claim of more packets. Kernel CPU savings do not equal whole-system savings.

## Live observation

The activation processed 120 aligned RF seconds during 120.8 seconds of observation and forwarded 501 coherent packets. Readsb, FR24, the combined relay, ADS-B Exchange and RF capture retain their original PIDs. Both coherent workers map the installed Rust library inodes; backend markers identify ordinary and pair builds.

Only shadow/DSP workers restarted. Stock feeding continued during the brief rescue pause. All gain, method, worker-affinity and protected configuration checks passed; receiver sample-loss/drop counters stayed at zero. FR24 remained connected with recent uploads. Neither neural model nor acceptance/routing logic changed.

RF capture remains enabled with PID 757, no current capture error, and the existing 5 GB cap (5,000,000,000 bytes). It was not stopped or forcibly flushed. Bounded RAM sampling and scheduled saves retain their prior behavior. Graceful shadow shutdown preserved its separate CRC research cache; archive bytes changed from 83,046,067 to 86,802,186. No historical archive was removed.

## Automatic rollback

The enabled guard checks every 15 seconds and restores the previous optimized C libraries after three consecutive unhealthy checks. It checks freshness, processing/stock progress, worker health, uploads, loss counters, repeated restarts and installed mappings/hashes. Normal startup gets a grace period. Activation has its own 120-second observation and rollback, plus a systemd failure handler. Guard status is stored in RAM; persistent state is written for release/rollback transitions.

Rollback restarts only adsb-rescue-shadow. It preserves readsb, feeders, relay, capture, gain, models, switches and caps. Rust is not automatically re-enabled after a rollback. This is an operational health guard, not an automatic RF accuracy oracle.

```sh
sudo /usr/local/sbin/adsb-coherent-rust-mode status
sudo /usr/local/sbin/adsb-coherent-rust-mode rollback
```

## Sources and evidence

[Production Rust](../../src/rescue/coherent_rust.rs) · [Build and deployment guide](../../experiments/rust-live/README.md) · [Pi release test](pi.json) · [Mac test](mac.json) · [Deployment](deployment.json) · [Guard status](guard-status.json) · [Capture status](capture-after.json) · [Rollback tests](guard-tests.txt) · [Integration tests](integration-tests.txt).

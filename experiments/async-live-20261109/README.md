# Asynchronous production activation — 9 November 2026

Authorized activation of the native-tested independent completion relay, with SIC
turned off. readsb, FR24, ADS-B Exchange and the far-RF collector remain running.
Only the relay and DSP coordinator restart for the new entrypoints. Receiver gain,
models, native/Rust libraries, other switches, collection policy and 5 GB cap stay
unchanged. The coordinator's ordinary stop saves its CRC research cache; no extra
recorder flush or archive deletion is requested.

`build.py` checks exact replacement sites against a captured **current deployed**
`shadow.py`, retaining its grouping, statistics, CRC quarantine, RF mirror and
training collection code. It creates additive `rescue.async_live_*` modules;
the existing modules stay intact. These reuse the race-safe completion tap,
causal admission, immediate relay and shared five-second/120 µs cache validated
under `experiments/async-native-20261109`. Every completed worker future can
publish independently. Stream1090 runs in its own bounded executor when stock
progress covers its RF window. Statistics can settle independently without
holding stock or producer output.

The integration uses bounded per-producer RAM outbox messages, one final emitter,
independent bounded client queues, and no intentional stock holdback. Stock
records from an already received TCP chunk share a queue entry; this prevents
large reads from exhausting queues before client writers can run. A 6,000-record
burst regression passes on Mac and Pi. Same-payload
later transmissions survive; only the same RF transmission within 120 µs is
merged. Stock bytes always survive. Extras retain original sample timestamps,
CRC/prior-stock/conflict/alignment gates and a three-second RF age limit. SIC,
header and broad CRC cannot leak into forwarding when disabled/quarantined.
Sequence/acquisition honor worker switches as well as normal method switches.

`activate.py` verifies live health, base-source identity and CRC-save headroom,
backs up exact configs/drop-ins and installs the rollback timer before cutover.
It replaces the earlier all-method budget guard with the new guard, retaining
its processing margin. The regular routing/fallback controller is paused during
the brief relay restart and resumed once the new stock output is ready. It does
not change FR24 configuration or restart readsb/FR24/collector/ADSBx.

`guard.py` runs every ten seconds, with a 100-second startup grace. It checks
status, methods, feeder connectivity, processing below 2.7 s (300 ms margin),
stock sample loss, cap/errors, outbox/cache overflow, late-stock duplicate races
and protected process identity within the activation boot. On reboot it checks
liveness rather than expecting previous boot PIDs. Three consecutive feeder
failures or a hard health failure trigger restoration of owned settings and the
old relay/coordinator entrypoints. Human changes are preserved. Only those two
services restart on rollback; previous guards are restored.

Manual rollback on the Pi:

```sh
sudo python3 /var/lib/adsb-async-live-20261109/guard.py --restore
```

Tests: nine deployable glue tests and two completion-race tests passed on Mac
and Pi; two additional rollback tests passed on Mac. Recorded native timing
replay through the deployable relay retained 319/319 extras with matching stock
bytes and no duplicates. `observe.py` performs a finite read-only socket check on
30005/31005, excludes five-second RF edge intervals, compares stock record bytes,
and checks extra duplicates with the same 120 µs tolerance. It neither opens the
SDR nor consumes the I/Q mirror. This is local transport evidence, not FR24 cloud
credit or a prospective range comparison.

`save_evidence.py` checksum-verifies and fsyncs private activation/config/status
and test evidence on the Mac. Public results are redacted under
`validation/async-live-20261109`; private data remains in adsb-neural-rescue.

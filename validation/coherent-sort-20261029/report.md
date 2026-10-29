# Coherent sort optimization is live

Activated 29 October 2026 on Raspberry Pi 5. Both coherent libraries now use a specialized C sort for pulse-magnitude quantiles. The change survives worker restarts and reboot.

This brings the useful sorting result from the Goose experiment into the C pipeline, without a Goose compiler/runtime, virtual stack reservations or new runtime dependency. The header adapts Goose v2026.3’s typed branchless sort; Apache-2.0 attribution and license are retained. Quantile ranks/interpolation, carrier/phase fitting, repair policy and acceptance guards are unchanged.

## Controlled replay

| Target | Coherent branch | libc µs/window | Typed C µs/window | CPU saving |
|---|---|---:|---:|---:|
| Mac M4 Max | ordinary | 8.648 | 6.482 | 25.1% |
| Mac M4 Max | pair-lag retry | 8.429 | 6.285 | 25.4% |
| Raspberry Pi 5 | ordinary | 26.279 | 20.403 | 22.4% |
| Raspberry Pi 5 | pair-lag retry | 25.527 | 19.444 | 23.8% |

Each comparison uses seven fresh-process trials on the same 3,269 windows from 42 previously consumed RF captures, including 32 seeded noise controls. The Pi reference also matches the actual installed libraries before replacement. All packet bytes, repairs, hard-decision scores, confidence, carrier estimates, inlier counts and flags match bit-for-bit. Both implementations produce 262 ordinary valid window outputs and 261 pair-lag outputs; these are separate branch results, not a loss or a count of unique extras. Noise controls remain rejected.

Two hundred thousand sort cases pass with address/undefined-behavior sanitizers on Mac and Pi, including every size 0–112, duplicates, ordered/reversed/adversarial values and the nonfinite libc fallback. The integrated native build and all 41 Python integration tests pass.

These are kernel CPU savings, not a measured 22–24% whole-pipeline reduction or a wattage measurement. The corpus is development regression data, not fresh reception validation. Larger input/output buffers make standalone process RSS about 19.5 MiB on Pi; ordinary reference and candidate have the same measured resident size, and retry differs by one 16 KiB measurement increment. There is no Goose runtime allocation.

## Live activation and health

Only `adsb-rescue-shadow` was restarted. Readsb, FR24, the combined relay, ADS-B Exchange feeder and far-range capture retained their existing PIDs. Both coherent workers map the new ordinary and pair-lag library inodes. All configuration hashes, method switches, gain, models and capture caps were preserved. The worker restart causes a brief gap in rescue work while stock continues through the unchanged relay.

The observation covered 90 aligned RF seconds in 90.8 wall seconds. It relayed 652 coherent frames and 1,249,354 stock bytes; 712 coherent frames were relayed across the complete cutover plus observation. FR24 remained connected with recent uploads. Sample-loss and dropped-sample counters stayed at zero. Backlog and latency health gates passed.

Graceful shutdown preserved the CRC research RAM buffer: archived bytes increased from 61,574,311 to 72,396,533, adding one archive. No old archive was removed. Independent RF collection stayed running; the existing 5 GB capture cap is unchanged.

## Rollback

Previous libraries and source are retained in the receiver backup directory recorded in [the deployment](deployment.json). To restore them:

```sh
sudo /usr/local/sbin/adsb-coherent-sort-mode status
sudo /usr/local/sbin/adsb-coherent-sort-mode rollback
```

Activation included automatic rollback on a failed health gate. The permanent command performs an explicit rollback; it is not a continuous watchdog. It restarts only the DSP shadow service.

## Reproduce and inspect

[Experiment instructions](../../experiments/coherent-sort/README.md) · [C sort](../../src/rescue/coherent_sort.h) · [Mac results](mac.json) · [Pi results](pi.json) · [Deployment](deployment.json) · [Input manifest](input-manifest.json). Private RF, binaries and generated scratch files are not committed.

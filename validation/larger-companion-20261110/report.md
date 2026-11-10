# Updated production companion and larger-network experiment

November 10, 2026 (Europe/Berlin).

## Production

The November 10 DSP-trained tiny companion is now appended to the original three-model cascade. Original-first priority preserves existing valid packets. The original model was not replaced. Its earlier validation showed four extra test windows but only one additional guarded RF message (100–150 nm, operational status); no distant RF improvement is established.

Activation preserved readsb, FR24, relay, ADSBx and collector process identities, gain, methods and collection limits. The coordinator alone restarted. The 150-second post-start observation passed, with 140 aligned blocks of progress and unchanged SDR loss counters. A three-entry provenance label tuple was extended before successful activation; an initial readiness race was caught by preflight. Rollback copies and an ownership-checked rollback helper remain on the receiver.

## Larger-network comparison

12 to 24 channels; 961 to 2,497 parameters. Raw and DSP-augmented variants were trained separately, 1,000 steps each. Validation-only selection preferred the raw variant for its one additional qualified distant validation window. No checkpoint was selected using RF or test results.

| Measurement | Updated production | + larger raw | + larger DSP-augmented |
|---|---:|---:|---:|
| Test-window complete packets (854 windows) | 647 | 647 | 660 |
| Extra qualified >=180 nm test windows | — | 0 | 3 |
| Full RF pipeline extras beyond stock | 260 | 260 | 260 |
| Unique RF additions beyond full production | — | 0 | 0 |
| RF baseline packet losses | — | 0 | 0 |
| Pi serial replay CPU seconds / RF second | 0.7312 | 0.7828 | Not target-tested |

Both larger variants were replayed on Mac. The validation-selected raw variant was also replayed on the Pi 5: packet digests and distance bins matched Mac exactly. It added 0.0458 CPU seconds per RF second for candidate inference alone. Total serial replay rose about 7.1%. Peak process RSS was 204.4 MiB. This is CPU time, not elapsed latency or measured power; replay repeats frontend work and starts Stream1090 per clip, so it is not a live utilization estimate.

No larger-model additions occurred in any distance bin, including >=180 nm, or beyond the previous best offline companion. Larger models remain offline.

## Controls and limitations

Each variant produced zero CRC-valid outputs on 20,000 noise windows, zero wrong CRC-valid outputs on 4,096 clean windows, and zero unexplained valid outputs on 4,096 overlapping synthetic windows. Each overlap control recovered one known secondary transmission. ONNX export changed no bits or packet bytes.

Training reused the established qualified dataset: 9,341 train, 1,793 validation and 854 test windows, including 503/197/224 recently qualified distant windows. RF evaluation used 383 snippets, 25.013 RF seconds (24.247 after edges), and only six quality-screened distant aircraft. RF intervals are evaluation-only and disjoint from training. These are reused established holdouts captured before checkpoint freeze, not fresh prospective validation. Accepted-production annotations are best-effort and incomplete; the comparison includes the full frozen enabled replay, actual relay and conservative annotation mask, but cannot claim complete production-ledger coverage.

The Pi benchmark was isolated, nice 19, core 3, 35% CPU quota, bounded runtime and process-tree memory checks. Receiver/feeder health was monitored. No candidate packets were injected. The baseline included enabled energy, timing, soft, matched, coherent, neural and Stream1090 paths; CRC predictions remain quarantined.

## Recommendation

Keep the updated tiny companion in production. More capacity improved some isolated windows, but did not produce additional full-pipeline RF packets. Collect fresh difficult distant examples before another architecture change; keep these evaluation intervals out of training.

Private weights, RF, activation evidence, exact source/input hashes and full replay results are retained in the private experiment directory. Only aggregate results are published here.

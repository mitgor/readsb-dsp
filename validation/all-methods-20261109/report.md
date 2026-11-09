# Guarded DSP methods enabled — 9 November 2026

**Enabled acquisition, sequence, pulse and SIC in the production combined feed, alongside energy, timing, soft, matched, coherent, neural and Stream1090. Header retry remains disabled.**

The all-method first attempt approached the existing3-second relay budget (maximum observed worker result latency 2.573s before Stream1090). The independent guard restored the former profile. Header retry had the largest newly added attributed CPU cost in that short attempt; disabling it produced the retained lower-latency profile. This is not an isolated ablation.

The retained profile completed 185 RF seconds during startup/live observation. Across 184.8s of fresh-profile snapshots, worker result/queue latency averaged 0.627s, maximum 1.011s. Stream1090's last runtime was 0.155s; its maximum sampled runtime was 0.171s. The maximum sampled sum of recent worker maximum plus latest Stream1090 runtime was 1.181s. This sum is a sampled proxy, not exact per-packet end-to-end instrumentation.

| Newly enabled method | Packets relayed during observed interval |
|---|---:|
| acquisition | 162 |
| sequence | 108 |
| pulse | 33 |
| sic | 9 |

Stream1090 relayed 404 packets in the same interval. These are source-attributed validated/deduplicated relay packets, not a frozen-baseline estimate of marginal recovery. Header relay delta is 0; old cumulative header counters from the first attempt remain historical.

No new late-candidate relay rejection was recorded in that observed interval (0); the retained DSP session reports 0 late Stream1090 skips. These short observations do not guarantee future traffic behavior.

The persistent budget guard checks every10seconds and restores the previous profile at a2.7-second sampled processing proxy, stale/failed worker health, increased radio sample loss or sustained feeder failure. The relay retains its independent hard3-second sample-clock deadline and rejects late candidate packets. Config ownership hashes prevent overwriting later human changes. Guard: `adsb-all-methods-budget-20261109-v2.timer`; source/backups: `/var/lib/adsb-all-methods-20261109-v2`.

Readsb, FR24, relay and RF collector retained their PIDs; FR24 remained connected. Only DSP shadow restarted. Stock sample-loss/drop counters are unchanged. Existing gain, Rust/native libraries, production models, original-first admission guards, RF capture settings and5GB cap are unchanged. Broad CRC remains research-only and cannot feed FR24. Main logging remains off as before; existing RF collection stays enabled. Graceful DSP shutdown preserved its CRC RAM cache within the existing archive cap; no saved archives were deleted.

Five guard threshold/ownership tests passed. Private checksum-verified activation snapshots retain both attempts and original method/worker configs. No new model, RF collection policy, feeder routing or cloud-credit behavior was introduced.

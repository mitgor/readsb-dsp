# Dashboard controls and Stream1090 CPU accounting fixed

The settings API returned HTTP 500 because the long-running controls service retained an old capture-policy validator loaded on October 29. A fresh process accepted the current 180 nm / 5 GB policy. Restarting the controls service loaded the current policy without changing capture settings.

The asynchronous integration omitted the old synchronous call to MethodMetrics.record_external. Stream1090 child CPU was measured but discarded when its independent future completed. The engine now charges it exactly once, including failed/unaligned or discarded-old-epoch work, and exposes a matching independent stream_child_cpu_s audit counter. Decoder algorithms, method switches and models are unchanged.

Verified through HTTP: GET settings 200; same-origin no-op POST 200 with byte-identical configurations and the same revision. No-op Apply now returns before rewriting files or restarting workers, preserving rollback ownership. Three regression tests passed on Mac and Pi: completed child charged once, old-epoch work charged, and no-op settings preserve bytes/revision.

| Stream1090 verification sample | Value |
|---|---:|
| Measured child CPU | 4.877 s |
| Mean CPU, one core = 100% | 12.17% |
| Worker/child CPU share | 13.53% |
| Attributed extras | 72 |
| CPU per attributed extra | 67.74 ms |
| Relative cost | 1.53× |

CPU increased across successive status reports and exactly matched the independent engine audit. Other method shares and relative costs now use the corrected denominator. This is attributed CPU cost, not an ablation measurement or electrical power.

The DSP coordinator and controls service restarted for this fix; dashboard CPU/detection counters began a new interval. Historical missing CPU is not retroactively reconstructed. readsb, FR24, the asynchronous relay, ADSBx and the RF collector retained their PIDs. SIC remains off; the persistent rollback guard is enabled and healthy. Gain, models, RF collection limits and 12-hour save policy are unchanged. Existing capture/CRC archives remain intact.

Neural development collection remains active: stock-confirmed >=180 nm snippets, original RF, and stock/unified Beast journals, bounded by the existing 5 GB cap. Qualification is still required before training; incomplete burst coverage stays flagged. The general historical experimental logger being off does not disable the dedicated far-training collector.

Private before/after source, metrics and status evidence is checksum-verified and durably saved on the Mac. Raw collection data and configurations are not published here.

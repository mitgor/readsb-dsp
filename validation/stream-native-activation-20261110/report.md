# Extended native Stream1090 activated — 10 November 2026

The working DSP Stream1090 branch now calls the extended native C++ library in-process. The original executable is retained as fallback. The branch keeps the same one-second windows, per-window trust reset, stock-derived clock calibration, CRC/address/conflict validation, deduplication, method attribution and relay routing. This activation does not implement incremental low-latency streaming.

## Validation and observation

- Exact complete-adapter rows and per-window alignment matched the original on all 119 Mac windows and 34 Pi windows (including the available distant-context cases).
- Forced native deadline errors replayed the same window through the executable exactly. Failed native decoding is not repeatedly retried. Bad library checksums fall back before loading. A one-microsecond deadline rejected all partial output.
- A native C ABI deadline checks between approximately 3.4 ms input blocks. Production reserves up to 0.5 seconds for native work and the remainder of the original one-second timeout for fallback.
- Isolated rollback tests restored exact original files, persisted executable selection, avoided restarting a healthy coordinator and required two consecutive health failures.
- The 120-second live observation recorded 128 successful native windows, zero native fallbacks and zero decoder errors. The mapped library inode matched the installed native file.
- The Stream1090 relay counter advanced from 49,488 to 49,841 during subsequent native-active checks, with the combined FR24 route and stock connection healthy. These are admitted relay packets, not raw decoder totals.

The prior saved-RF kernel benchmark measured 24.5% lower method CPU with the same recovery. The deployment adapter's CPU telemetry now includes the calling thread as well as child CPU, so its counters are not directly comparable to the previous child-only telemetry. The new adapter preflight is a parity/fallback gate, not a new like-for-like CPU benchmark.

## Continuity and limits

Readsb, FR24, the relay, ADS-B Exchange and the far RF recorder retained their original PIDs. Only the DSP coordinator restarted once to load the adapter. Its bounded CRC RAM logs had ample disk-save capacity and were preserved through graceful shutdown. No collection archive was deleted, and the 5,000,000,000-byte RF limit remains unchanged. Models, method switches, workers, gain, feeder routes and protected configurations were unchanged.

The recorder stayed running and its collection counters advanced. Across the preflight/handover observation interval it recorded 8,512,720 additional RF-tap gap samples, equivalent to 3.55 seconds of RF. This is a gap in the copied RF tap, not an increase in primary SDR sample loss. It is not a claim of a gapless mirror handover. Existing buffered data was preserved.

## Automatic rollback

The adapter fails over to the original executable for native errors, invalid outputs, overflow, checksum/ABI failures or deadlines. The independent `adsb-stream1090-native-guard.timer` is enabled at boot and checks every approximately ten seconds. Healthy watchdog heartbeats stay in RAM to avoid periodic SD writes; only state transitions are persisted. Idle feeders are allowed to have no recent aircraft uploads when no aircraft are tracked. Two consecutive bad checks persistently disable native use and restore the original adapter files. It monitors coordinator readiness/restarts, feeder connectivity, protected PIDs/configuration, workers, gain, primary SDR counters, archive/recorder health and installed native hashes. A healthy coordinator can return to executable decoding without a restart; a dead or stalled coordinator is restarted after restoration. Protected feeder/receiver/recorder services are never restarted by this tool.

Manual rollback:

```sh
sudo /usr/local/sbin/adsb-stream1090-native-mode rollback --reason manual
```

Status:

```sh
sudo /usr/local/sbin/adsb-stream1090-native-mode status
```

The status JSON field `stream1090.backend` is `native`; the reported `binary` path continues to name the fallback executable. Persistent rollback backups remain on Pi and have a checksum-verified durable Mac copy. Temporary preflight files were removed only after verification. No raw RF, private diagnostics or credentials are included in this public report.

# deadsb dsp integration validation — 29 October 2026

This is source integration evidence, not approval to replace a working receiver.

- Mac ARM64: complete file-only and RTL-SDR-enabled readsb builds passed.
- Mac: 41 controller, dashboard, worker, ring, streaming and bundle tests passed.
  This includes suppressing both shared-ring worker roles and recovering without
  a missing-producer wait, plus rollback of temporary per-job settings.
- Native CRC/CPR, DSP guards and ASan/UBSan checks passed on Mac.
- Isolated Raspberry Pi 5: readsb file-only build, 13 worker native libraries,
  CRC/CPR, native DSP guards, and 10 governor/dashboard tests passed.
- Pi work ran nice 19, CPUQuota 35%, core 3, MemoryMax 1G, bounded runtime, entirely
  in an owned tmpfs directory. No SDR or production I/Q mirror was opened.
- New full-profile output matched the original runtime and Pi byte-for-byte by
  candidate timestamp/payload/method digest on the same already-consumed RF.
- That RF check is only **54.6 milliseconds with nine energy candidates**. It
  checks integration wiring, not weak-signal recovery, distant benefit, sustained
  throughput, optimal package choice or power consumption.
- Stock readsb, FR24, relay, collection and ADS-B Exchange PIDs stayed unchanged.
  The rescue coordinator PID changed concurrently; this task issued no production
  service operations. This is not an uninterrupted whole-pipeline health test.
  No live model, configuration or capture cap was changed by this integration.

Aggregate evidence is in [deadsb-20261029/](deadsb-20261029/summary.json). No raw RF
or per-aircraft logs are included. The earlier native-only release's longer
replays remain separate evidence, with their original limitations.

The governor's 55% target / 60% ceiling is **cooperative**, with overload/recovery,
stale telemetry and temperature logic tested by deterministic simulation. A
sustained hardware shadow trial spanning real overload, thermal throttling,
recovery and substantially more distant RF is still required. Budget reductions
can lose rescue extras. Stock is preserved by a separate primary readsb process,
not by assuming every reduced DSP profile is packet-equivalent to full inference.

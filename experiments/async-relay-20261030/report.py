import argparse,html,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();O=a.output;probe=json.loads((O/'passive-probe.json').read_text());replay=json.loads((O/'event-replay-mac.json').read_text())
for name in ['async-tests-mac.txt','async-tests-pi.txt','event-tap-tests.txt','event-tap-tests-pi.txt','handover-tests.txt','monitor-tests.txt','cadence-tests.txt','previous-regressions.txt']:assert (O/name).read_text().rstrip().endswith('OK'),name
summary=dict(stage='test_version_not_production',stock_test=dict(end_berlin='2026-11-01T20:00:00+01:00',review_berlin='2026-11-01T20:15:00+01:00',measurement_hours=60,extended_by_hours=48,fr24_reconnect_during_extension=False),relay=dict(independent_source_channels=12,history_seconds=5,history_capacity=100000,stock_holdback_s=0,max_extra_age_s=.25,real_dsp_producers_attached=False,fr24_or_adsbx_attached=False),passive_probe=probe,event_replay=replay,tests=dict(transport_mac=9,transport_pi=9,event_callback_mac=2,event_callback_pi=2),limitations=['Passive target probe contains original stock only, no live DSP producer','No full-current-pipeline fresh-RF extra-retention validation yet','250ms age gate may reject slow valid results','Stock-first priority cannot retract an already emitted extra; race counted','CPU/RSS includes test recording, health checks and heavy Python imports','Epoch mapping and original producer admission must be integrated before live use'])
(O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
text=f'''# Asynchronous relay test and 48-hour baseline extension

FR24 stock-only feeding is extended until **Sunday, November 1 at20:00Berlin**, for60measured hours total. The review is scheduled20:15Berlin. The independent restoration guards are November1 19:02UTC and19:10UTC. Monitor handovers did not reconnect FR24 or restart readsb/DSP/relay/capture/ADS-B Exchange; gain, switches, models and5GB RF cap stay unchanged.

## Relay test version

Independent bounded queues support all12DSP source channels, including neural,
coherent and Stream1090. Missing/slow producers do not block stock or other
producers. Slow output clients are disconnected independently. The single output
path preserves frame bytes and RF timestamps without timestamp sorting/holdback.

The shared cache retains transmission identity for5seconds (bounded100,000entries),
with epoch/payload/RF-time matching and120us tolerance. Legitimate repeat payloads
at different RF times survive. Stock is always preserved and late-stock races are
counted. BroadCRC and provisional/unverified callbacks cannot enter the feed.
Current method switches, alignment, CRC, prior-stock identity, duplicate/conflict
and freshness gates remain required.

Completed-future taps avoid an all-workers barrier. Event callbacks can expose
energy results before later stages finish. Fused native DSP calculations still
share their work; asynchronous delivery is not a promise that all algorithms run
independently. Callback failure does not alter returned decoder outputs.

## Validation

- **11tests pass on Mac and target Pi**:9async transport/contract/future tests and
  2event-publication tests. Additional handover, quiet-RF monitoring, credential
  redaction and7previous prototype regressions pass locally.
- Historical reserved RF regression: **113raw decoder events unchanged**, with all
  **92allowed candidate callbacks** matching exactly. The21other raw events are
  BroadCRC, excluded from these callbacks. This is a limited energy/CRC/timing/
  soft/matched regression, not full-current-pipeline new-detection evidence.
- Fresh45second target passive probe: **{probe['stock_core_records']:,}stock records
  in the interior window, {probe['missing_stock_core_records']}missing**. Median
  client-arrival difference **{probe['delay_seconds']['median']*1000:.2f}ms**, p95
  {probe['delay_seconds']['p95']*1000:.2f}ms, p99
  {probe['delay_seconds']['p99']*1000:.2f}ms. These are localhost receipt-time
  differences, not RF-to-cloud latency. No DSP producer or feeder was attached.
- Probe process CPU{probe['process_cpu_s']:.3f}s over{probe['wall_s']:.2f}wall seconds
  (~{probe['equivalent_one_core_percent']:.2f}%of one core), including dual TCP
  recording, status and health checks. PeakRSS{probe['peak_rss_kib']:,}KiB includes
  Python/NumPy/decoder imports; this is not cache-only memory or DSP computation.
  It is not a like-for-like production CPU improvement claim.

Tests/probes used nice19/core3/35%quota/1GiB/finite runtime on the target. Protected
service identities/configuration, stock route and loss counters passed. The first
Pi run exposed an asyncio cancellation cleanup race, fixed in the subscriber
shutdown path. Subsequent network fixtures incorrectly assumed packet order and
omitted a prior-stock sighting; corrected fixtures exercise the existing guards,
which were not relaxed. All failed attempts are retained privately.

## Daily cadence evidence

A separate read-only audit backfills numeric send/config/overlap/time-sync events
from the measured interval. It uses bounded RAM and12hour/final disk saves,
independently of RF capture. The baseline sender configuration is30s/30s, mode1,
filtering enabled. The first audit could not parse an ISO-style journal date;
revision2 uses journal-compatible UTC dates and backfills the missing interval.
Those were diagnostic query errors, not feeder failures. No uploader configuration
was changed. Daily server adaptation is a hypothesis, not an established fact.

## Before any live relay activation

This relay remains separate from FR24/ADS-B Exchange and has no production DSP
producer connection. Integrate causal producer admission and native receiver/
connection epoch mapping, then measure real extra ages/additions/losses for every
current enabled method on fresh reserved RF. The250ms freshness ceiling can lose
slow valid extras, and late-stock races cannot be undone after emission. Replay
the measured schedules through the isolated FR24 binary before a reviewed live
condition. Finish the extended stock-only test without mixing in this change.
'''
(O/'report.md').write_text(text);(O/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Async relay test and extended baseline</title><main style="max-width:1100px;margin:2em auto;padding:20px;font:17px/1.6 system-ui"><pre style="white-space:pre-wrap">'+html.escape(text)+'</pre></main>')
print('Report generated.')

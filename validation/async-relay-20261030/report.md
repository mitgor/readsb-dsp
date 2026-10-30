# Asynchronous relay test and 48-hour baseline extension

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
- Fresh45second target passive probe: **31,793stock records
  in the interior window, 0missing**. Median
  client-arrival difference **1.10ms**, p95
  3.40ms, p99
  52.57ms. These are localhost receipt-time
  differences, not RF-to-cloud latency. No DSP producer or feeder was attached.
- Probe process CPU4.861s over50.15wall seconds
  (~9.69%of one core), including dual TCP
  recording, status and health checks. PeakRSS114,560KiB includes
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

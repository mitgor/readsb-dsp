# Asynchronous relay test and extended stock baseline

The working feeder/DSP/model/collection setup is unchanged. FR24 continues direct
stock input30005 until **2026-11-01 20:00 Europe/Berlin (19:00UTC)**, extending the
original end by48hours and the measured baseline to60hours. Stock-only does not
mean all stock messages are independently verified physical truth.

## Test relay

`async_relay.py` has independent bounded queues for energy, timing, soft, matched,
coherent, sequence, acquisition, header, SIC, neural, pulse and Stream1090.
One absent/slow source does not hold the others. Stock is enqueued immediately,
without a global timestamp ordering holdback. Each output client has its own
bounded queue; slow clients are disconnected without blocking the others.

A shared five-second cache keys receiver/session epoch, payload and RF timestamp,
with120us duplicate tolerance. Identical payloads at genuinely different RF times
survive. Capacity is bounded100,000entries, with TTL/capacity counters. Every stock
byte survives; late stock after an emitted extra is counted, not silently dropped.
Original timestamps remain unchanged. Five seconds is history, not output delay.

Only already-admitted producer messages may enter: `producer` names the channel,
`batch` contains `admission=production_guarded_v1`, current epoch, created_unix,
verified alignment (>=20matches, median<=2us), and up to256`extra` rows with matching
source, message_hex and ticks. The relay independently rechecks current switches,
CRC, prior stock identity, conflicts, sample-clock duplicates and250ms freshness.
The marker is a local producer contract, not a cryptographic proof. Raw callbacks,
Broad CRC and unverified research output are never feed inputs.

`completion_tap.py` exposes completed worker-method results without waiting for a
slow coherent future, while preserving original full-group collection/statistics.
`event_tap.py` can observe runtime event creation before later neural/classical
stages finish. Its callbacks are provisional/unadmitted; callback failure does not
change decoder results. Fused C/Rust stages still finish their shared computation
together; no redundant frontend work is introduced just to call them independent.

This version is **not wired to production workers or feeders**. Producer-side
causal admission, genuine receiver/session epoch mapping and full enabled-pipeline
fresh-RF parity remain integration gates. The standalone listener's epoch is a
connection-session token, not automatically the SDR process PID. The250ms ceiling
may drop slow valid extras and is not a universal FR24 guarantee.

Run tests with the existing project Python and PYTHONPATH=src:

    python -m unittest discover -s experiments/async-relay-20261030 -p test_async_relay.py -v
    python -m unittest discover -s experiments/async-relay-20261030 -p test_event_tap.py -v

Finite passive server (new owned runtime directory and explicit test switches):

    python experiments/async-relay-20261030/async_relay.py --runtime /tmp/owned-new-relay-test --switches /tmp/test-switches.json --seconds 60

The output binds loopback on an ephemeral port listed in endpoint.json. Production
output/input ports are forbidden as listeners. Producer IPC is a600-mode Unix
socket. Nothing edits feeder routing or owns an SDR/mirror consumer.

## Stock test extension

The original monitor had an immutable12h deadline. `extend_trial.py` retires only
that owned monitor, temporarily keeping its restoration target on the already
active stock route until its finally/ExecStopPost finish, then restoring sealed
combined-restoration metadata. All metadata/samples are backed up first. FR24 and
protected service PIDs are verified unchanged. `revise_monitor.py` applies the
same handover to a quiet-RF-aware monitor: progress requires actual RF processing,
not a minimum aircraft/alignment count. Original interruption records are retained
as superseded monitor phases, not feeder outages or completed baselines.

Active monitor: adsb-fr24-stock-extended-v2-20261030.
RAM: /run/adsb-fr24-stock-trial-20261030/extended-status.json.
Independent restore guards: November1 19:02UTC and19:10UTC. Normal routing guard
remains enabled for reboot. User manual routing intent is respected. Scheduled
review moved to November1 20:15Berlin. No second live condition is auto-enabled.

`cadence_audit.py` retains numeric sender/config/overlap/time-sync events in bounded
RAM and saves every12hours/final closure. Active revision2 unit is
adsb-fr24-stock-cadence-v2-20261030; durable output cadence-audit-v2 within the owned
trial directory. It backfills the measured period from journals, with a separate
initial30s/30s sender-config snapshot. No raw log text/credentials/RF are saved by
this audit. The first audit's date-format failure and failed test attempts remain
preserved separately. The working receiver was unaffected by these diagnostic
failures. Daily cadence adaptation remains a hypothesis to measure.

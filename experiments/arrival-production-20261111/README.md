# Arrival-order relay and incremental Stream1090 production activation

The normal combined Beast endpoint stays at127.0.0.1:31005. When
/etc/default/adsb-relay-arrival.json selects enabled=true, rescue.feed dispatches
to rescue.arrival_feed. It uses the arrival-output policy exercised in the
November11 production trial, with one stock reader and one outbox reader.
Subscribers have independent bounded queues. There is no timestamp-ordering wait.
Original stock bytes and timestamps are preserved; the shared five-second cache
rejects the same transmission across extra methods. Distinct repetitions remain.
All existing source switches, CRC, stock-only address/conflict, epoch and clock
audits remain required. Broad CRC research never enters this output.

The max_extra_age=3seconds is an eligibility limit for existing slower methods,
not a three-second output delay. The cache's five seconds is a memory lifetime,
not a batching interval. Downstream consumers must tolerate original RF timestamps
arriving out of order. Local TCP delivery does not prove cloud acceptance.

Stream1090 uses the previously validated incremental native library with20ms
chunks and existing energy completions. Models, gain and other DSP methods stay
unchanged. The deterministic replay-control change explicitly creates an incomplete
window before testing its retirement; it no longer assumes a background thread
has published the next tail-window event. This changes the harness, not decoder
inference. The isolated replay may use half-speed arrival to fit the35% CPU cap;
it is a parity gate, not evidence of real-time throughput at that cap.

The independent arrival relay timer checks protected services, RF loss counters,
settings, component hashes, stock connection, feeder connection and status ages.
Two failed checks select the original ordered relay and restart only that relay.
The separate incremental watchdog disables the native path and restores the
original coordinator source; a stalled coordinator may be restarted. Its recorded
failure now includes separate DSP/relay status ages and native queue/error/counters.
Original15s DSP and6s relay freshness thresholds are retained. Neither watchdog
changes the5GB capture cap or12-hour collection schedule.

The activation script pauses the incremental guard during the intentional relay
restart, then updates only its expected relay PID after protected health passes.
A persistent timer provides rollback if activation is interrupted. Reboot resets
process identity baselines only after verifying normal health and unchanged
configuration. Raw RF, device config, journals and rollback backups remain private.

Run offline controls with python3 controls.py. The repository's
 tests/test_arrival_feed.py checks lossless stock, backward-time extras, duplicate
and epoch rejection, late-stock preservation, receiver configuration handling and
large upstream bursts. Old asynchronous protocol tests remain separate; they
require a different outbox contract and are not substituted for the live contract.

Manual relay rollback on the receiver:

    sudo /usr/local/sbin/adsb-arrival-relay-mode rollback --reason manual

Manual incremental rollback:

    sudo /usr/local/sbin/adsb-stream1090-lowlatency-mode rollback --reason manual

No raw RF, sharing key or receiver configuration should be committed.

## Activation findings and fixes

The initial production reactivation reproduced a43s-old DSP report while the
relay report was0.3s old. Both guards reverted. This establishes a stale DSP
status, not by itself a native decoder deadlock. The coordinator wrote status
only at the bottom of its processing loop, below multiple early-continue paths
(unaligned/stale/no-context windows). The patch now places that same checkpoint
at the loop head. A control executes repeated continue paths and proves they
still publish status. Inference/admission calculations and guard thresholds are
unchanged. A one-shot14s Python stack dump is armed at each status checkpoint
into /run/adsb-rescue/coordinator-stall.log, giving RAM-only evidence if reporting
or the coordinator stalls again.

Earlier checkpoint publication also exposes expected incomplete startup health
fields. Native activation waits for a complete gain/latency snapshot within its
existing readiness deadline. The arrival guard recognizes only that bounded,
explicit native activation state while still checking relay readiness and
capture health. It resumes its full health checks automatically afterward.
No general runtime failure or timeout receives this startup exception.

The two-hour isolated soak was not completed; it is not a deployment proof.
A corrected packet-parity gate and a six-minute real production observation are
used for this activation, followed by permanent watchdogs and anomaly monitoring.

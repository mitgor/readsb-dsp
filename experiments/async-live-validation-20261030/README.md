# Real DSP output validation (isolated Pi transport)

Read PROTOCOL.md first. The finite observer reads original stock30005, actual
combined31005 and inotify notifications for published feed-outbox JSON. It never
consumes/writes production outbox entries or opens SDR/mirror inputs. Two isolated
fan-in objects compare unchanged250ms and explicit3s freshness using actual
producer arrival times; current whole-second grouping is preserved.

Source model/library hashes, PIDs, config, gain, RF losses, collection and the
stock-only FR24 route are checked. Output is owned tmpfs; no feeder is attached.
Nice19/core3/35%CPU quota/1GiB/300s maximum;35s warmup +180s measurement +5s tail.
Do not rerun into the fixed owned path: preserve it and adapt to a new dated path
for a new experiment. No thresholds/models are tuned on this capture.

`analyze.py --input PRIVATE_DATA --output PUBLIC_AGGREGATES` verifies every member
hash and produces counts, reference coverage, timing, CPU deltas and estimated
range. Use `--private-cohort PRIVATE_FILE` only for a private detailed evaluation
record. Never commit/publish the captured packet/cohort/position files. No I/Q is
captured and no data from this test qualifies as supervised training labels.

`report.py --output PUBLIC_AGGREGATES` is the frozen dated report generator for
this run, with expected packet-count assertions. Do not overwrite prior results.

The3s diagnostic matches all4,592current-relay cohort extras;250ms retains none.
This does not validate early per-method publication or FR24 tracking semantics.
Keep the extended FR24 stock test and working pipeline unchanged. Read the report
limits before interpreting CPU percentages or the54estimated far-range packets.

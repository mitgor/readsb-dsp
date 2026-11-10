# Asynchronous output in the installable workflow

`readsb-dsp shadow` and the installer use `rescue.async_shadow`. The relay unit
runs `rescue.async_feed` with explicit methods and worker configuration paths.
Both are normal package modules with no imports from dated experiments, private
workspace files or receiver-specific deployment helpers.

Readsb remains the sole SDR owner. A completion tap observes each finished native
worker future before the ordinary RF-second grouping consumes it. Cheap DSP and
coherent futures can publish independently. Algorithms sharing a worker still
share its computation; asynchronous output does not create a thread per filter.
Grouping continues separately for statistics, RF journals and training quotas.
The CPU admission governor still controls each admitted job.

Admission requires fresh stock context, at least 20 matching energy/stock clock
anchors with median absolute error at most 2 microseconds, valid DF17 CRC,
causal stock-established identity and the existing conflict checks. Output uses
bounded RAM outbox files, preserving original RF timestamps. No research CRC
hypothesis enters this output. Disabled methods, including SIC, stay disabled.
Sequence/acquisition also require their worker switches to be enabled.

The relay sends stock immediately and unchanged, including opaque bytes and
original duplicate stock frames. Each downstream client has a bounded independent
queue; a slow client disconnects instead of blocking the others. Extras must pass
the guarded producer contract and be no more than three RF seconds old. A shared
five-second history rejects the same payload within 120 microseconds across
producers. A later transmission carrying the same payload is retained. If stock
arrives after an already forwarded extra, stock still wins: the stock frame is
preserved and the race is counted, not silently discarded. This policy does not
promise global timestamp ordering or eliminate that unavoidable late-stock race.

Stock upload cadence/cloud credit is controlled by the feeder/provider; this
local relay does not make a guarantee about FR24 hit counts.

## Scope and validation

The promoted completion tap, admission and relay originate in the validated
November 9 live experiment. The package integration retains the public bundle's
native methods, frozen models, governor and logging policy. Standalone Stream1090
is not packaged here, so there is no implicit external executable dependency.
The working receiver's separately deployed `async_live_*` modules are untouched.

Package regression tests cover future-completion races, admission-to-outbox-to-
relay recovery, cross-method duplicates, repeated payloads, stock byte preservation,
6,000-record TCP bursts, method switches, epoch changes, disabled SIC/broad CRC and
missing alignment. Existing full native/worker/governor tests also apply. These
are transport and integration checks, not new RF recovery or FR24 cloud evidence.
CI additionally builds and renders the full inactive installation on Linux.

## Explicit legacy fallback

Keep the coordinator and relay paired: the two outbox formats differ. During a
planned change, stop both units, preserve their configuration, and wait for any
normal logging shutdown to finish. Start a legacy coordinator with
`python -m rescue.shadow` and relay with `python -m rescue.feed` (same runtime,
methods and output port; legacy relay defaults to three-second holdback). Remove
only stale outbox notifications belonging to the stopped pair, never RF archives.
The inverse restores the async pair. Do not run two relays on the same port or
mix an old coordinator with the new relay. Readsb and feeder configuration need
not change. Recording buffers require their ordinary safe shutdown/headroom;
this guide does not authorize forced flushes or archive deletion.

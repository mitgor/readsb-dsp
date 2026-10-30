# Real admitted DSP relay validation — October30

Before viewing results, compare frozen default250ms freshness and diagnostic3s
freshness on identical live already-guarded producer results, at their actual
publication/observation times. Both use immediate stock, original timestamps and
the same shared5s/120us dedup cache. No tuning of models/DSP from this capture.
The diagnostic is not a recommended deployment or proof of FR24 acceptance.

Observe original stock30005, actual combined31005 and read-only inotify MOVED_TO
notifications for feed-outbox. Never remove/rename/write/hold any production
outbox entry, change source/relay/routing or use SDR/mirror inputs. Record every
inotify read miss/overflow; do not claim complete producer coverage if any exist.
Observe at least30s stock history before the180s measured interval and drain5s
of output afterwards. Fixed enabled methods captured before/after; disabled
methods remain disabled. All candidate output isolated/quarantined.

For each method count observed producer-admitted extras, matches in actual relay,
250ms/3s asynchronous emissions, output differences and stock duplicates/races.
Cross-source dedup uses transmission identity, not payload-only5s suppression.
Attribution is first accepted source at arrival, not causal algorithm ablation.

Measure stock arrival/output delay, producer->relay-output delay, and DSP event RF
age relative to latest observed stock sample-clock watermark. The latter has
stock-stream scheduling uncertainty and is not RF-to-cloud latency. Get existing
exclusive method CPU from live metric deltas; measure experimental relay calls
and total observer process CPU separately. No extra DSP inference is run.
Distance uses prior stock position age<=15s with NIC/NACp>=5 and no MLAT/TIS-B;
otherwise unknown. RF CRC validity is not independent physical truth.

Nice19/core3/35%CPU quota/1GiB/finite runtime. Monitor protected PIDs, source/model/
config hashes, gain, stock-only FR24 route, extended-trial/cadence guard status,
SDR losses and collection health. Abort only the owned observer if protected
health degrades. Preserve5GB cap and normal flushes; checksum-backup owned files
before cleanup. No deployment, feeder injection or external messaging.

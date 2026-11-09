# Fresh isolated asynchronous relay check — 9 November 2026

Follow-up to the October30 discussion/prototype. Production keeps its3-second
holdback and current DSP methods; this test does not route FR24 or ADSBx.

`start.py` snapshots current receiver Python source into an owned RAM directory,
adds the existing async prototype and starts a finite read-only probe at nice19,
core3,35% CPU,256MiB,120s maximum. It reads stock30005 and combined31005 and
compares them with an isolated ephemeral-loopback async stock relay. No live DSP
producer is attached. `probe.py` retains wire/chunk arrival evidence and checks
protected PIDs/config hashes/methods/gain/stock loss and FR24 connectivity.

First attempt used /dev/shm; the owned tree disappeared during execution, so its
journal-only failed outcome is retained and excluded. Cause unconfirmed. Retry
uses a new /run RAM directory and succeeds. No networking, access, service
configuration, models or capture policy changed.

`finish.py` checksum-verifies and durably copies closed owned evidence to the
private workspace. `analyze.py` compares complete core transmission multisets and
local arrival latency, verifies health and publishes only redacted aggregates.
Nine async transport/dedup tests pass on both Mac and the target Pi. The Pi tests
use only synthetic/local sockets, never live feeder injection.

Production's full DSP producer admission, real receiver epoch mapping, old250ms
prototype age policy and fresh full-pipeline extras/loss parity remain integration
gates. This is a stock-transport measurement, not a full DSP asynchronous trial
or evidence of FR24 cloud acceptance. A shared5-second transmission cache is
history, not a wait, and preserves real repeated payload transmissions.

See `validation/async-check-20261109/summary.json`. Raw data and source snapshots
are private. Owned closed temporary files are removed only after verified Mac
backup and rechecking their remote hashes; production data is never removed.

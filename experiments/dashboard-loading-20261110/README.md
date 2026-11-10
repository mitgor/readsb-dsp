# Dashboard loading fix — 10 November 2026

Both URL prefixes served correct JSON. Receiver loopback requests took about
0.5 ms, but Mac LAN transfers of the 278 KB status took 10.1–11.2 seconds during
the investigation. Roughly 197 KB of its unindented content was the detailed
`crc_research_recent` array, unused by the statistics page. Requests were serial
and unbounded, so a hung request blocked subsequent refresh cycles.

The web control backend now exposes `/readsb-dsp/api/dashboard-status` and the
legacy alias. This projects only dashboard fields without changing source status,
counters, models or collection. The full status.json remains available unchanged.
The deployed page is versioned at `dashboard/statistics.html`. Panels poll
independently, with eight-second fetch/body timeouts and per-panel in-flight
limits. Both aliases request the canonical endpoint. No decoder configuration,
web settings mutation, recording flush or feeder restart occurred.

After deployment: response 13,631 bytes, Mac LAN fetches 0.376 and 0.087 seconds.
Both pages visibly populated stock/extras, distance/CPU tables and method controls.
All six protected service PIDs were unchanged. Only the loopback web-control
service restarted. An initial immediate readiness probe raced startup, triggering
web-only rollback; the successful second attempt uses bounded readiness polling.
Originals remain under `/var/backups/readsb-dsp-dashboard-loading-20261110` and
`/var/backups/readsb-dsp-dashboard-loading-20261110-v2` on the receiver.

Tests: compact projection preserves counts and excludes raw research records;
Node VM executes the actual dashboard with a permanently stalled capture request
and verifies statistics/controls still load and statistics can refresh again.
Reproduce with `node tests/dashboard_loading.cjs`. Deployment helper is dated and
receiver-specific, hash-guarded, and refuses overwriting its backup directory.

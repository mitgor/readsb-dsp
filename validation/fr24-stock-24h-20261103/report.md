# New 24-hour stock-only FR24 trial — 3 November 2026

User explicitly requested another 24-hour stock-only condition. FR24 is directly connected to readsb port30005, bypassing custom relay additions and holdback. The established I/Q-tapped readsb executable remains unchanged; this is a stock-output routing test, not a pristine-binary replacement.

Started: 2026-11-03T18:10:51.393120+01:00.
Planned automatic combined31005 return: 2026-11-04T18:10:51.393120+01:00.
First120seconds excluded from analysis. Only complete UTC cloud hours wholly inside the settled condition qualify; do not count the transition buckets as pure stock or claim24h success before closure.

Preserve desired DSP intent. Normal feed guard paused for the trial but remains enabled for reboot recovery. Two independent systemd restore timers at deadline+2min/+10min, plus finite monitor finally restoration and runtime bound. Restore respects a new manual routing intent. Protected readsb/DSP/relay/collection/ADSBExchange processes/configs/gain unchanged; only FR24 restarted once for route change. RFcap5GB and normal12-hour saves preserved. No forced flush or archive deletion in this activation.

Inherited strict safety guards include unchanged SDR loss/drop, protected PIDs/configs, healthy DSP/relay/capture and connected FR24 after settling. Quiet RF does not require artificial aircraft traffic; stale sends only fail when aircraft are tracked. Further SDR loss will abort and restore early, as in the previous trial, and must be reported explicitly. No automatic trial retry/extension.

Owned receiver state: /var/lib/adsb-fr24-stock-trial-20261103 and /run/adsb-fr24-stock-trial-20261103; monitor unit adsb-fr24-stock-24h-20261103. Local source, initial snapshot, summary and four passing safety tests preserved here. RAM snapshots every60s, own durable checkpoint12-hourly and final closure; monitor logs hourly numeric progress. Existing collector buffers unaffected.

# Official FR24 native receiver trial — closed review, 9 November 2026

**The stock decoder did not restore pre-drop FR24 hits/positions during the observed35-hour condition. The planned48-hour trial stopped early; this is not a complete48-hour result.**

Measurement began7 November12:00UTC (13:00Berlin). On8 November23:00:01UTC the feeder logged `syncing stream: timeout`, followed by disconnect at23:00:02. The once/minute health monitor detected the disconnected link at23:00:29 and restored the original setup by2026-11-08T23:00:40.943807+00:00. This was a feeder-link timeout, not evidence that the native demodulator failed. Other transient disconnects had reconnected before health sampling. No new condition was launched.

## Restoration verified

All14 managed original paths match their saved state. Readsb, FR24, combined relay, ADSBx, DSP and RF collector are active; DSP/collector retain their original PIDs and are thawed. FR24 is connected through the restored configuration. Gain remains38.6dB and the RF cap remains5,000,000,000bytes. The collector reports no error. No forced buffer flush or archive deletion was performed.

## Cloud statistics read from signed-in browser

| UTC date | Condition | Aircraft | Positions | Hits | Maximum nm |
|---|---|---:|---:|---:|---:|
| 2026-11-05 | Before trial | 1,581 | 96,748 | 588,834 | 226 |
| 2026-11-06 | Before trial | 1,632 | 112,044 | 967,420 | 347 |
| 2026-11-07 | Mixed: native from11:52; measure from12:00 | 1,296 | 89,159 | 695,188 | 225 |
| 2026-11-08 | Native until23:00, then restored | 1,556 | 107,943 | 917,411 | 228 |
| 2026-11-09 | Restored; partial day | 1,128 | 57,997 | 442,016 | 227 |

The visible hourly chart was read through rendered SVG coordinates, using its displayed linear axis. Every daily hits/positions total equals the sum of its24 reconstructed hourly points (10 exact checks). November9 future zero points are not measured zero reception. No hidden app/session data or authenticated API was used.

## Matched UTC hours

There are35 nominal complete native measurement hours:7 November12–23 and8 November00–22. A conservative34-hour chart-label comparison excludes7 November12 because the label boundary convention is unresolved. Each earlier date is weighted with the same hour list, including repeated morning/evening hours.

| Baseline date, same34-hour weights | Trial hits | Baseline hits | Change | Trial positions | Baseline positions | Change |
|---|---:|---:|---:|---:|---:|
| 2026-11-05 | 1,149,173 | 884,369 | +29.9% | 142,983 | 143,660 | -0.5% |
| 2026-11-06 | 1,149,173 | 1,449,086 | -20.7% | 142,983 | 166,768 | -14.3% |

These comparisons do not establish causality: they are not randomized or traffic-matched. Against October26 pre-drop cloud credit (10,153,060hits and1,748,894positions), November8 remained in the same low-count regime as the post-drop period. November8 was not a full native day; its23:00 hour is excluded from native matched-hour totals. No evidence supports an order-of-magnitude credit recovery after switching to official FR24 DVB-T input.

## Local reception, cadence and interruption evidence

The same native decoder PID persisted throughout sampled exposure, with 2,068 health samples and maximum sample gap 61.07s. Last native counters show 51,882,134 accepted messages, 3,647,427 global CPR successes and zero samples dropped since decoder startup; these are not48-hour totals or FR24 cloud credit.

The journal contains 4,182 `sent … AC` events during measurement: median interval 30.038s,95th percentile 30.147s, maximum 118.076s. There were 15 stream timeouts and 5 disconnections, and 2,077 overlap-filter log events. Configuration messages before/after measurement show30s/30s sending, maximum age15s and filtering enabled. Local feeder activity cannot prove which packets the cloud credits.

The CSV/JSON include local RRD integration, explicit finite-data coverage and interpolated native counter changes. RRD and native counter semantics differ across receiver implementations; ratios are not packet-loss rates. Native counter changes require bracketing samples within90seconds; missing boundary data remain null.

## Interpretation and next evidence

The observation weakens the claim that the current readsb/DSP relay alone is sufficient to explain the persistent low credit: low cloud counts also occur with official native input bypassing it. It does not rule out earlier stream-quality/account effects, stock payload quality, backend overlap selection, or cadence/accounting policy. The remote timeout explains why this trial closed, not the original October27 drop.

Keep the restored working pipeline unchanged. The most useful next evidence is FR24 support explaining receiver-side overlap filtering/cloud-credit policy and the account’s server-side changes around October27. No support message was sent automatically. A further controlled trial needs separate authorization and a predefined disconnection tolerance, rather than silently extending this incomplete condition.

## Preservation

Closure evidence: 2,025,532bytes, SHA-256 `91799037578672217b9568604a3c6a9e07c33d2006563d0396bcd37dae82c96b`, 21 verified members, including lifecycle state, exact source/config rollback records, RAM health samples, hourly checkpoints and trial-period journals. Full logs/configs remain in the private incident case because they contain the sharing key. This public report contains only redacted results. Earlier failed attempts and the aborted October31 trial are preserved and excluded.

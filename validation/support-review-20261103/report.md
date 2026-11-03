# FR24 support replies, peer research and final receiver evidence — 3 November 2026

Support reference 787205. Two original user-supplied screenshots are preserved privately with checksum manifest. Support first suggests duplication due to a bad decoder/router state and rebooting; the later reply suggests the earlier higher counts were inflated by duplicates. Support says no change was made to this setup from their end, only latest settings are visible, and their comparable history older than seven days is unavailable. These are support hypotheses, not a measurement establishing duplication on this receiver. No support reply was sent by this agent.

## Independent peer statistics

Read the signed-in, shared visible statistics for German feeder T-EDDS1060, id24228, through the normal date selector. Current partial-day values excluded. No hidden page/network state read.

| UTC date | Aircraft | Hits | Positions |
|---|---:|---:|---:|
| 28 October | 3,777 | 9,856,448 | 1,124,452 |
| 2 November | 3,758 | 8,781,658 | 1,038,239 |

Source: https://www.flightradar24.com/account/feed-stats/?id=24228 . This is a high-ranked Stuttgart-area receiver, not a matched nearby control. Antenna, traffic, gain, decoder and residence times differ. The currently visible seven-day selector starts28October, so it cannot establish whether that receiver changed on27October. The observations show multi-million counts exist elsewhere; they neither prove our earlier counts correct nor exclude duplicates in either receiver. No generalized network-wide incident established.

## Public documentation and first-person reports

- FR24 official statistics guide defines hits as aircraft-to-receiver updates regardless of content, positions as reported aircraft positions, and aircraft seen as daily distinct Mode-S codes. It does not disclose duplicate accounting or exact counter transport/credit implementation. https://www.flightradar24.com/files/Documentation_Feeder_Statistics.pdf
- Public leaderboard uses30-day uptime/range statistics updated12-hourly. It is not a historical hits/positions dataset suitable for diagnosing27October. https://www.flightradar24.com/share-statistics
- In a2019 first-person thread a user reported roughly90% upload filtering after startup. A contributor said hits/positions were internally counted independently of overlap suppression. That is historical community testimony, not confirmation of current1.0.57-1 behavior. https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/12459-feeder-filtering-most-data-from-upload
- FR24 staff explicitly acknowledged missing/broken feeder statistics from routing problems inJune2018. Demonstrates a historical statistics failure mode, not a current incident. https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/11595-problems-with-feeder-statistics-and-data-sharing
- A2020 ADS-B user reported positions120,000→7,000, but aircraft also declined1000→400–500; user later suspected a tilted antenna. Unlike our largely stable local reception. https://www.reddit.com/r/ADSB/comments/ie4fz0/
- A2026 Plane Finder user reported positions290,000→150,000 and later said support fixed insufficient upload frequency. Different service/protocol, so only an analogy. https://www.reddit.com/r/planefinder/comments/1uciohj/significant_drop_in_plane_finder_receiver/

## Receiver findings completed today

Checksum-copied all38owned closed-trial files from durable and RAM directories, including both cadence audits, baseline config, extension and restoration receipts. Private TAR14,151,680bytes SHA256015d03d40a90f72dd06d695223a8840d909afafb0f5bd47a455dacd672f4f7a4. Original failed query audit preserved as diagnostic-tool error.

Revision2 cadence audit closed normally1November19:00UTC:7191send events3572overlap events. Median send intervals30Octoberstock30.010s;31Octoberstock30.011s;31Octobercombined30.015s;1Novembercombined30.016s. No>45s gap in the saved stock phase, one in1Novembercombined. Baseline and restoration configs30s/30s, maxage15s, mode1, filteringtrue. This does not establish27October cadence, and literal send fields are not packet counts/cloud credit. No day-boundary cadence change observed in this test.

Retained raw fr24feed journal query for30October06:50–1November19:15UTC returned zero records: journal rotation/coverage missing, not evidence of no activity. Saved numeric cadence and trial snapshots remain the available period evidence.

Fresh live check: combined31005, desiredDSP, normal guardactive, receiver/feedconnected, ringnotfull, timingvalid, gain38.6. Same readsb/DSP/relay/capture/ADSBExchange PIDs as1November; feederPID456334 unchanged. SDR lost now589824 versus262144on1November, dropped0: additional327680samples (~0.137RFseconds at2.4Msps), time/cause not established. Do not attribute the original90%cloud discrepancy to this small cumulative count. Collector running, errornull, cap5,000,000,000bytes preserved. No live restart/config/route/model/collection change. Expired trial deadline/safety timers already unloaded; stop requests confirmed notloaded and normal guardremainsactive.

## Interpretation and next discriminating question

No direct evidence currently proves historical duplicate inflation. Stable unique aircraft is compatible with duplicates but also with reduced update accounting, reporting/filtering issues or intermittent delivery, so it does not distinguish them. Our sampled strict stock/relay audits found no duplicate/conflict flags; those samples are incomplete and cannot establish all historical traffic. Direct stock for26.85measuredhours did not restore earlier cloud/local indices. Support's proposed historical-inflation explanation remains testable, not established.

Most useful clarification for support: what exactly was duplicated (identical Beast transmission, repeated legitimate payload, duplicate feeder session or statistics report), at what stage, and can they compare our current hit/position counters with a nearby receiver normalized by aircraft contact time? Ask whether the reported numbers are all local receptions or filtered/deduplicated upload credit. Request specific evidence before rebooting/reverting multiple components. No external message sent and no new live test initiated.

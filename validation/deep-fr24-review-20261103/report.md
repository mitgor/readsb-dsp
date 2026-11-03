# Data transfer, current feed and FR24 research — 3 November 2026

**The data transfer is complete. FR24 currently receives the combined relay, not direct stock-only readsb. No live configuration was changed.**

## Transfer

Downloaded ten immutable archives totaling **500,813,642 bytes**. Each Mac backup was verified by size and SHA-256 and made durable before the exact Pi file was rechecked and deleted. Five archives contain RF captures; five contain CRC research data. Active buffers remain in RAM until their normal saves. The 5,000,000,000-byte RF cap is unchanged.

All RF archive member checksums pass. The captures offer 903 distant stock training windows, which still require independent label qualification. All 7,841 CRC research I/Q windows remain quarantined. The 1,685 continuous RF segments are globally reserved for evaluation only. No model was trained or deployed.

Mac destination: `data/raw/pi-offload-20261103`. Manifests, scripts and audits: `results/daily-20261103` in the private workspace.

## Current routing and deduplication

`readsb:30005 → existing combined relay:31005 → fr24feed 1.0.57-1`

The feeder monitor, configuration and established socket agree. ADS-B Exchange also receives port 31005. FR24 has one local process, a connected receiver and server link, valid timing and synchronized OS time.

- Stock packets are preserved by the relay. There is no custom stock deduplication or reduced-output flag in the running arguments.
- DSP/neural extras pass the established validation and duplicate checks. Identical payloads within 120 microseconds of the same recorded transmission are rejected as extras; repeated legitimate transmissions at later RF times are retained.
- The existing three-second ordering holdback is still active. The isolated asynchronous/Rust relay experiment has not been deployed.
- The receiver executable is `readsb-rescue-stream`, containing the established I/Q tap. It is not a pristine upstream binary; preserving stock packets downstream does not independently prove full binary equivalence.

A fresh 45.14-second passive probe compared 15,413 stock frame instances in the 36-second interior window. **Zero were missing** from the relay, matching record type, payload, timestamp, signal and multiplicity. Median delay was 3.015824 seconds, p99 3.092692 seconds. These are localhost receipt times, not cloud latency. Protected service PIDs, configurations and SDR loss counters were unchanged during this work.

The stock-only trial ended automatically on 31 October at 09:52 UTC. It is not currently running.

## Closest comparable reports

1. **2021: stable local reception, lower FR24 positions after a feeder upgrade.** A user reported hourly positions falling from roughly 10,000 to 4,000 while hits stayed around 21,000 and local graphs stayed similar. Their follow-up reported recovery after actually restarting on an older feeder version. This is the strongest analogy for feeder/version or reporting differences, but it is an uncontrolled historical report and does not justify installing obsolete versions. [Initial report](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/202924-rpi-v1-2-running-fr24feed-v-1-0-23-8-should-i-upgrade), [follow-up](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/202924-rpi-v1-2-running-fr24feed-v-1-0-23-8-should-i-upgrade/page2).

2. **2019: heavy filtering starts after startup; restarting helps temporarily.** The user reported approximately 90% filtering. A contributor said hits and positions were internally counted separately from overlap suppression. That is historical community testimony, not confirmation of the current implementation. [Thread](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/12459-feeder-filtering-most-data-from-upload).

3. **2019: different FR24 results from the same decoder.** A Dutch first-person report describes reduced hits/positions with normal aircraft counts, healthy other feeders, and differences between feeder IDs and versions. Later native/container comparisons did not isolate a container cause. This illustrates confounding, not a proven key or account fix. [Report and follow-ups](https://gathering.tweakers.net/forum/list_messages/1524421/28).

4. **2018: FR24 acknowledged broken statistics.** Staff documented routing problems and missing/broken feeder statistics on 14–18 June. This establishes a historical platform failure mode, not a current incident. [Staff announcement](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/11595-problems-with-feeder-statistics-and-data-sharing).

5. **21 October 2026: several feeders suffered HTTP 503 errors.** Multiple users, including one on 1.0.57-1, reported configuration-download failures followed by automatic recovery that afternoon. This happened six days before our drop and involved disconnections, so it is not evidence of the same cause. [Thread](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/234074-fr24-link-disconnected-http_error-503).

6. **Other recent reports have distinct symptoms.** A 19 October report describes suspected DNS failure coupling; a 24 October dropout report is unresolved. The 26 October missing-directory startup warning explicitly does not prevent the service from running, although staff acknowledged it for correction. These are differential checks, not diagnoses of our statistics drop. [DNS](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/234037-dns-lookup-in-fr24feed-broken-for-certain-replies), [dropouts](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/234129-constant-feed-dropouts), [startup warning](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/234143-bug-fix-fr24feed-service).

7. **Thirty-second cadence exists elsewhere.** A 2024 feeder seeing more than 3,000 aircraft daily posted a 30s/30s sender configuration. No verified explanation was provided. Our saved stock/combined audit also remained around thirty seconds; that alone does not establish a penalty. [Thread](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/225434-send-interval-question).

## Assessment

The search covered official documentation, first-person FR24 forum reports and staff responses, readsb issues, other community forums and Reddit. No public evidence establishing a widespread 27 October collapse or duplicate inflation in our receiver was found. Unindexed or private reports may exist.

FR24's [official guide](https://www.flightradar24.com/files/Documentation_Feeder_Statistics.pdf) defines hits as aircraft-to-receiver updates, but does not specify duplicate accounting, exact counter transport or upload-credit rules. Stable aircraft counts are compatible with several explanations and do not prove duplicates. The failed recovery during 26.85 measured stock-only hours weakens a simple immediate relay-only explanation; it does not prove a server fault.

The most useful next evidence is a precise definition of the current counters and a nearby-receiver comparison normalized by aircraft contact time. A separate controlled test would be needed to distinguish a pristine receiver binary, feeder version and reporting state. No reboot, downgrade, key change, new live condition or support message was performed.

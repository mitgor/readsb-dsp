# Twenty-minute live RF comparison: native phase search and Stream1090

**Decision:** Keep the current Stream1090 integration. The native clean-CRC
subset is not a drop-in replacement: it missed many valid-CRC payloads emitted
by the full upstream decoder and absent from stock. The native search also
found a smaller distinct set, which merits further shadow validation before
any feeder routing. No receiver switch or FR24 routing was changed for this
test.

## Capture and method

- Live receiver: Pi at `192.168.2.195`; research-only RSC1 I/Q mirror over SSH
  to the Mac. Capture ran 2026-10-29 **17:49:05–18:09:05 CET**, exactly 1,200
  wall seconds. The stock and unified Beast streams were independently copied.
- 1,195 complete RF seconds were replayed. Five I/Q discontinuities excluded
  about five seconds of complete-window coverage. The final partial transport
  frame at the hard cutoff was ignored; earlier frames passed CRC32 checks.
- Both decoders received the same 1-second UC8 windows, with 600 input samples
  of context on each side. The old program was built on the Mac from
  `mgrone/stream1090` commit `2189bdaca1d62d5e88600b21a281ccc5c18012f2`
  and invoked as `stream1090 -s 2.4 -u 8`, matching the active method. Native C
  came from `readsb-dsp` commit `6834980`. Exact payloads within 120 µs were
  deduplicated. All compared messages are CRC-valid DF17 after decoding.
- Beast comparison used 180,211 candidates within coverage of both paired
  streams. The observed native-preamble-to-stock clock offset was **2,400
  12-MHz ticks**, with median absolute deviation **1 tick**. Paired coverage
  excludes the first few seconds before the Beast tap connected.

| Result | Shared by both | Native only | Stream1090 only |
|---|---:|---:|---:|
| Distinct DF17 events, all usable RF | 129,031 | 31,983 | 20,604 |
| Events in paired Beast coverage | 128,009 | 31,724 | 20,478 |
| Absent from **stock** Beast | 1,490 | 651 | 7,919 |
| Absent from unified Beast | 118 | 305 | 569 |

The total stock-absent candidate count was **2,141 native** versus **9,409
Stream1090** (shared candidates counted once for each method). The 651
native-only stock-absent events are an upper bound on potential additional
recovery from running both. Of the 305 native-only candidates absent from the
unified feed, 283 had a prior stock address sighting; this is context, not
the full production guard or independent packet truth. None of those 283 was
at 200 nm or farther in a fresh receiver-position snapshot; this run does
not validate long-range benefit.

Measured **Mac decoder CPU** was 21.84 seconds for native C versus 64.96
seconds for the per-second Stream1090 child processes over the 1,195 RF
seconds, about 1.83% versus 5.44% of one core. The native path used 66% less
CPU here, but it also implements less of the algorithm: clean DF17 only,
without Stream1090's repairs and trust policy. These are not Pi CPU figures.

The rescue shadow service restarted at 2026-10-29 17:01:52 UTC during a
separate receiver change. Stock readsb stayed active and its clock alignment
remained stable, so the stock comparison above is the primary conclusion.
Unified-feed absence is reported as context; the restart and associated
transition can affect it. Before/after counters are in `final-paired.json`.
The FR24 relay process stayed the same; readsb, `adsb-rescue-feed`,
`adsb-rescue-shadow` and `fr24feed` were active with fresh stock traffic at
each check. The Mac research helper was restored after capture.

## Reproduce

The scripts are `readsb/tests/dsp-rescue/compare_stream_phase_live.py` and
`analyze_stream_phase_paired.py`. This directory retains small summary JSON.
The full private RF mirror (`live-rf.framed`, 5.75 GB), paired Beast copy
(`paired-beast.bin`), and per-window candidate JSONL remain only in the local
checkout's validation directory; they are not committed to GitHub. Their
per-window RF SHA-256 digests are in the candidate JSONL. No aircraft location,
feeder key, or raw RF was published.

The next meaningful decoder step is a bounded, separately validated port of
Stream1090's repair/trust behavior, followed by another same-RF paired replay.
Until then the native phase method should remain off on the Pi.

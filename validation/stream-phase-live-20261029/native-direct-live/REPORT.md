# Direct live old Stream1090 versus native phase comparison

**Result:** On the same 1,148 complete live RF seconds, native phase repair
recovered **15,512 of 17,503 (88.625%)** packets emitted by the pinned old
Stream1090 binary but missed by native clean decoding. This closely replicates
the earlier saved-RF result (88.5%). Of 6,740 such old-only packets absent
from stock readsb, native recovered **5,327 (79.036%)**.

The old executable emitted 117,986 unique CRC-valid DF17 events. Native clean
and repair combined matched **115,995 (98.3%)** of them within 120 µs and
missed **1,991**. Native also produced **43,226** events absent from the old
executable, including **10,105** absent from stock. These native-only events
are candidates, not independently verified packets, and were not routed to
FR24. The old integration remains needed for the 1,991 unmatched events.

## Method and health

The Pi 5 research observer received a nonblocking copy of the working SDR's
UC8 stream. For each identical one-second RF window, it invoked the pinned
old Stream1090 executable (`2189bdaca1d62d5e88600b21a281ccc5c18012f2`,
`-s 2.4 -u 8`) and native C with the CRC-table and confidence repairs.
This is the same old binary and per-second invocation used by the working
integration. Each window required at least ten shared clean frames and a
stable median clock offset before exact-payload pairing within 120 µs. The
measured median residual offset was −1 sample-clock tick; maximum median
absolute deviation was 1 tick, and the weakest window had 54 shared clean
frames. Per-window aggregates summed exactly to the final status counters.

The observer ran 1,200 seconds and completed 1,148 RF windows (95.7% coverage).
It recorded 115 research-copy IQ discontinuities, zero research queue-shed
seconds, and zero old or native decoder errors. The production tap had a
brief 5,536-sample drop during the run; its counter then stayed flat. Stock
readsb and FR24 stayed active with fresh feed status and no upstream error.
The receiver process kept PID 4694. After the run, the temporary IQ mirror
drop-in was removed, `adsb-rescue-shadow` was restarted with its original
Mac-helper command, and the research service remained disabled at boot.

## Interpretation

This confirms the native port recovers most of the old decoder's additional
DF17 output under a **direct live same-IQ comparison**. It also shows why
native cannot replace the old integration yet: 1,991 old packets were not
matched. Agreement between two algorithms on one receiver's IQ is not
independent packet truth. The much larger native-only set is especially
uncertain; previous random-IQ controls admitted CRC-valid repair candidates.
The comparison is before production prior-ICAO, conflict and deduplication
checks. Keep the old Stream1090 integration feeding as it is and keep native
repairs in research shadow until a stronger false-positive gate exists.

Only this report and [`public-summary.json`](public-summary.json) are
versioned. Per-window aggregates and IQ remain local. The observer, limits
and rollback are documented in [`docs/LIVE_PHASE_SHADOW.md`](../../../docs/LIVE_PHASE_SHADOW.md).

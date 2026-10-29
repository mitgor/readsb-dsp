# Experimental native realtime DSP rescue

This branch integrates the DSP-only contrib reference into readsb's native sample
processing path. It is **off by default**, needs no Python/runtime dependencies,
and contains no neural inference, weights or training code. The existing receiver
was not modified or restarted. This is a separate follow-up to the offline
contribution in PR #163, not an update to that PR.

## Operating modes

- No extra flags: stock decoding/output; no extra I/Q allocations or copies.
- `--dsp-rescue`: **shadow mode**. Stock messages alone reach tracking, stdout and
  network outputs. Rescue candidates are counted separately.
- `--dsp-rescue --dsp-rescue-output`: explicitly permits guarded additions through
  the usual `decodeModesMessage` / `netUseMessage` path. Existing network settings
  determine their destinations. This is not enabled on the working receiver.
- `--dsp-rescue-budget-us N`: 100–50000 microseconds per input buffer; default
  min(5000 microseconds, 10% of the buffer's RF duration). A cooperative wall-time
  budget, not a hard realtime deadline or an OS CPU quota.
- `--dsp-rescue-log FILE`: buffered candidate audit JSONL, for offline validation.
  It contains timestamps, payloads, method and guard result. Disk I/O can block;
  leave unset for live use. Summary counters go to stderr on exit.

Only 2.4MS/s RTL-SDR UC8 and UC8 `ifile` input are supported. Other SDRs,
network-only mode, SC16/SC16Q11 files and dependent options without `--dsp-rescue`
are rejected. No new ports, feeder changes or service modifications are made.

A local-file shadow run in this separate build directory:

```sh
make -j2                         # no SDR library needed for ifile
./readsb --device-type ifile --ifile capture.uc8 --iformat UC8 \
  --raw --mlat --dsp-rescue > stock-only.txt 2> shadow-summary.txt
```

Add `--throttle` to pace the file at its original RF rate. Add
`--dsp-rescue-output` only for a separate local-file output comparison. Without
network flags, these runs have no network outputs. Do not replace the installed
binary or open the SDR already owned by the working receiver for these tests.
RTL-SDR builds require a clean build: `make clean && make RTLSDR=yes -j2`.

## Native pipeline and bounded scheduling

An optional reader-side UC8 copy travels in the existing magnitude-buffer FIFO,
including 326 input samples of history at the current sample rate. The reader
publishes both buffers together; the decode thread never reads an SDR callback's
transient pointer. Memory is allocated once at startup, not per candidate.

Stock Mode S demodulation runs first. Rescue runs cooperatively on the same
thread, so no worker mutates tracking/network state concurrently. It skips live
rescue when more than two SDR buffers are queued, discarding rescue work instead
of queuing it. The ifile path intentionally permits unthrottled replay. There
are no new worker threads; this does not promise unchanged stock latency on
arbitrary hardware.

The FIR uses absolute sample positions, preserving 5/3 interpolation phase even
when input buffer lengths are not divisible by three. Half-open start ownership
crosses chunks and SDR buffers. Scratch chunks contain complete packet/FIR/timing
context. Artificial initial history and context after sample loss are excluded.
Discontinuities reset pending, duplicate and stock identity state; no packet is
assembled across a known sample gap.

All four methods are native C:

1. Clipped-energy PPM slicing on the shared normalized-preamble/FIR front end.
2. Six fractional timing retries using the existing C sinc interpolation kernel.
3. Unique one/two-bit repair from at most six weak bits; confidence <=0.35,
   at most 21 hypotheses; bits 0–31 (DF, CA, ICAO) remain protected.
   `--no-fix` disables this method. Otherwise its explicit DSP limit is two
   weak bits; the existing stock single-bit correction limit is unchanged.
4. Preamble-derived carrier estimate and complex matched filtering.

No relaxed-header search, interference cancellation or broad CRC search is added.
Expensive retries are capped at 32 failed header-screened windows per 50ms RF and
8 per scratch chunk. Windows are visited chronologically, unlike the offline
tool's strongest-first selection. Deadlines are checked between small work units;
one FIR chunk, hypothesis, guard scan, scheduler pause or I/O call can overshoot
the cooperative budget. Counts can vary when deadlines expire.

Scratch is fixed (8192+504 complex samples). Stock history holds at most 16384
DF17 records; pending/accepted caches each hold 2048 events. Full pending queues
drop candidates, not stock. The module has roughly 1MiB of static state, plus two
UC8 bytes/sample in each of the existing 12 SDR buffers when enabled. No
capture-sized candidate list or unbounded worker queue exists.

## Acceptance, timestamps and statistics

Candidates wait until the next buffer's stock pass, allowing stock to decode
boundary-spanning frames before duplicate decisions. Guards require valid DF17
CRC and a prior **uncorrected stock DF17** sighting of the same ICAO within 30s.
Same payloads within +/-120us and different same-ICAO payloads within +/-4us are
rejected against stock and previously accepted additions. Additional messages
never establish identity. Cache eviction can reject useful candidates
conservatively; stock identity and CRC are not independent RF truth.

UC8 and magnitude buffers share the reader sample clock. Rescue timestamps use
stock's end-of-bit-56 convention, including its historical-buffer offset; no TCP
arrival-time fit or offline clock offset is needed. The file tests preserve every
stock `(timestamp,payload)` record. Additional latency is one input buffer
(about 27.3ms for 65536 samples). Final pending candidates are discarded without
a following stock pass; a short/empty final buffer also discards them.

Counters `raw` / `extras` are ordered energy, timing, soft, matched. `extras` is
the guarded, deduplicated union; `forwarded` counts actual native submissions
after decoder checks. JSONL includes released candidates and duplicate rejects;
pre-release drops appear only in counters. The initial stream start counts as a
discontinuity. Shadow processing does not mutate tracking or CRC identity state.

RF signal/noise/gain counters stay stock-only in shadow mode. With output enabled,
accepted rescue packets increment `demod_accepted` by repaired bit count; they do
not contribute another RF noise/signal estimate or preamble/phase count.
Downstream tracking sees the union. RF graphs are therefore not per-method
rescue statistics; consult the rescue summary separately.

## Validation and limits

Commands are in `tests/dsp-rescue/README.md`. On macOS arm64:

- Normal and clean RTL-SDR-enabled builds succeed.
- Standard CRC/CPR tests and all 14 contrib reference tests pass.
- Native guards, weak-bit, capture/history and streaming tests pass ASan/UBSan.
- Eleven synthetic packets across five subphases and six buffer boundaries are
  recovered once, with zero extras and no missing stock records.
- The paired 10-second capture has 6272 stock records / 1403 DF17. Disabled and
  shadow output preserve every stock timestamp/payload. Explicit local-file
  output adds **70 DF17**: 34 energy + 17 timing + 16 soft + 3 matched, with no
  missing stock. This is about 5% additional DF17 on this single interval.
- Shadow rescue work is about 0.565 seconds / 10 RF seconds on this Mac. A 100us
  budget discards most rescue work while preserving all stock records.
- A separate paced-file shadow run preserved all 6272 stock records and counted
  61 extras; it spent about 0.910s in rescue and hit the cooperative deadline in
  168 buffers. This illustrates the recovery/budget tradeoff and hot-cache vs
  paced scheduling differences, rather than a hardware RTL-SDR benchmark.
- Generated uniform noise (0.2s) and shuffled I/Q (10s) yield zero raw rescue
  candidates. These controls do not establish an operational false-positive rate.

The offline reference counted 75 additions on this recording. Native scheduling,
retry order, edge ownership and final-buffer conservatism differ; exact candidate
parity with the offline scheduler is not claimed. There is no independent RF truth.
The private recording is excluded; SHA-256:
`0bd2525ea34e40ffd8c06973986110bcf609b1e55adfe4c5491cff499a9d8576`.

**Before live deployment:** shadow profiling of a separate Pi 4 build on the
actual RTL-SDR path; sustained overload/sample-drop/temperature checks; longer
receiver/noise controls; and review of timestamp, scheduling, statistics and
acceptance semantics. No Pi hardware performance result is claimed here. The
working receiver remains unchanged.

SPDX-License-Identifier: GPL-3.0-or-later.

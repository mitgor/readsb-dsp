# Native DSP integration checks

Run from the readsb checkout. No tests access SDR hardware, feeder services or
network outputs. ASan/UBSan need GCC/Clang support. The replay harness uses NumPy
only to generate fixtures; readsb itself has no Python dependency.

```sh
make -j2
make test
make dsp-rescue-test
make dsp-rescue-test-sanitize
make -C contrib/dsp-rescue test PYTHON=/path/to/python-with-numpy-scipy
```

Build a separate untouched stock checkout at
`9460652952a62fcfd9bf11a2664d737147f266a5`. Then:

```sh
python3 tests/dsp-rescue/replay.py \
  --readsb ./readsb --stock-readsb /path/to/stock/readsb \
  --capture /path/to/private-2.4MSps.uc8 --output /tmp/native-validation.json
```

Omit `--capture` for generated fixtures alone. The harness checks every stock
(timestamp,payload) record against disabled, shadow, output-enabled and 100us
budget modes. Stock must be preserved in each, with no non-stock output in
shadow/disabled modes. Explicit output's added count must match `forwarded`.
It also tests eleven synthetic packets (five sample subphases and six buffer
boundaries), uniform noise, shuffled real I/Q and six invalid configurations.

`unit.c` tests prior-stock-only identity (including future/expired/repaired stock
rejection), duplicates, conflicting messages, shadow isolation, explicit output,
wall-budget discard, discontinuity reset, live backlog skip, one/two-bit header
protection, UC8 history copying, short-buffer native bounds and global FIR phase.
It also checks phase repair's separate research deduplication ring cannot
suppress working output. `repair_unit.c` checks the rolling CRC basis and a
bounded three-bit erasure solution; both run under ASan/UBSan.
It includes the private implementation to inspect caches without exposing a test
API in readsb. The normal network/decoder functions are stubbed in that test only.

The standalone unit executable is ignored by Git. Never commit private UC8,
per-aircraft audit logs or timestamped receiver output. Aggregate validation
results can be shared separately. Upstream ifile currently exits 1 at EOF; the
harness checks actual records and rescue summaries in addition to the exit code.

`trace_stream1090_provenance.py` instruments only a clean pinned upstream
checkout for offline comparison. `classify_stream_phase_gap.py` separates
clean, fixed-table, erasure and DF19 output on the saved live capture.
`replay_stream_phase_repair.py` then tests the native repair port on the same
RF, using only preceding stock Beast addresses as a permissive prefilter.
`bench_stream_phase.c` measures standalone CPU cost from an offline UC8 file;
it never opens a receiver or feeder socket. Native phase repairs require
`--dsp-rescue-stream-phase-repair` and remain shadow-only even if general DSP
output is enabled.

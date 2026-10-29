# Production coherent quantile sort

The Goose comparison found most of its speedup came from its specialized sort.
`src/rescue/coherent_sort.h` adapts Goose v2026.3's branchless typed sort into C,
with attribution and its Apache-2.0 license in `docs/licenses/`. The working
pipeline requires neither a Goose compiler nor a Goose runtime. Only coherent
quantile sorting changes; carrier fitting, thresholds, packet repair, guards,
shared frontend and routing are unchanged. Both ordinary and pair-lag coherent
libraries use the new path by default.

Finite arrays up to 112 doubles use insertion sorting for small partitions,
a branchless median-pivot partition, equal-key handling, bounded explicit stack
and a depth-limited heap fallback. Nonfinite or larger arrays retain libc
`qsort`. The interpolation expression and quantile ranks remain unchanged.
Define `RESCUE_REFERENCE_SORT` at compile time to retain the original sort.
The earlier Goose experiment explicitly defines that macro to keep its original
C baseline reproducible after this optimization.

## Tests and replay

```sh
cc -O1 -g -fsanitize=address,undefined -Isrc/rescue \
  experiments/coherent-sort/check_sort.c -lm -o /tmp/check-sort
/tmp/check-sort
python experiments/coherent-sort/prepare.py \
  --input /path/to/already-consumed/shared-feedback-20261028 \
  --output experiments/coherent-sort/.work/windows.bin
python experiments/coherent-sort/benchmark.py --output /tmp/mac-sort.json
```

Use project Python with NumPy and existing native frontend libraries. Preparation
selects up to 96 chronological windows from each of the 42 saved development RF
files and adds 32 deterministic noise controls. This is implementation regression,
not fresh reception validation. Private RF/windows stay in ignored `.work/`.

For Pi, stage the same tree with `src/rescue/coherent_kernel.c`, its new header,
`experiments/goose-coherent/driver.c`, the two check/benchmark files and fixture.
Run the benchmark under nice 19, core 3, 35% CPU quota and bounded memory/runtime;
`--live-root /home/pi/adsb-neural-rescue` also requires exact parity against both
actual installed libraries. It builds isolated `.so` files and does not deploy.

CPU is process CPU per presented window, excluding initialization and I/O; seven
fresh-process trials alternate order. All diagnostics, not only packet outputs,
must match bit-for-bit. Every noise control must be rejected. Sanitizers cover
200,000 sort cases with sizes 0–112, repeated/ordered/reverse/adversarial values
and nonfinite fallback. See [results](../../validation/coherent-sort-20261029/report.md).

## Activation and rollback

`tools/coherent_sort_mode.py` performs a separate explicit deployment. It checks
benchmark parity, installed baseline hashes, a speedup gate and receiver health;
backs up both libraries and source; atomically replaces them; and restarts only
`adsb-rescue-shadow`. Graceful shutdown saves its CRC research RAM archive when
there is room under the existing cap. Other RF capture remains running. A
90-second health observation checks protected PIDs, configuration hashes,
method switches, gain, backlog, mapped library inodes, sample counters, FR24 and
progress of stock/DSP/coherent forwarding. A failed activation restores the
previous files automatically and restarts shadow again.

On the receiver:

```sh
sudo /usr/local/sbin/adsb-coherent-sort-mode status
sudo /usr/local/sbin/adsb-coherent-sort-mode rollback
```

Rollback restores exactly the prior two libraries and source, including the
prior absence of the sort header. It does not alter gain, method selection,
models, routing or capture caps. Persistent copies make the optimization survive
normal worker restarts and reboots.

# Distant training capture and verified offload

A collector-only update, 29 October 2026. Readsb, the DSP/neural decoder, models,
gain, method switches, relay and both feeders are unchanged. Only far capture was
restarted; its old RAM cache was saved, copied to Mac, verified and then removed
from Pi along with the earlier saved datasets.

## New capture policy

The receiver configuration uses a 180 nm threshold, 256 MiB batch RAM, 128 MiB
continuous RF allocation, the existing 5,000,000,000-byte hard SD dataset cap and
43,200-second bulk-save interval. At the disk cap, capture pauses; it never
overwrites archives. The separate existing CRC archive retains its prior cap.

Continuous RF is sampled across UTC hours (about 1.98 seconds/hour for this RAM
allocation) and stays evaluation-only. Closing-marker reserves prevent ordinary
RF/metadata from taking the memory needed to close journals. Flush refuses
unfinalized bursts. Full stock/actual-relay journal coverage is still required
for a continuous burst to be useful for unqualified incremental comparisons.

A new 48 MiB training reserve captures original 2 ms stock packet windows even
when the continuous RF quota is exhausted. Three distance bands each admit at
most 80/hour, two/minute. Each aircraft admits at most one/minute and 24/hour.
Admission is bounded by RAM, SD capacity and available qualified stock traffic.
Actual throughput can be much lower; these are caps, not promised example counts.

Labels originate only from same-transmission CRC-valid stock DF17 frames, with
original Beast bytes, original UC8 checksum, exact sample/timestamp metadata,
gain and a causal stock position. NIC/NACp>=5, no MLAT/TIS-B coordinates and
position age<=15 seconds are required. External context, later packet repetition,
and DSP/neural predictions do not supply training labels. Reported range is not
independent physical ground truth.

Snippets overlapping retained continuous evaluation RF are skipped. Quotas survive
a clean collector restart; minute bookkeeping stays bounded. New v3 tar archives
include training.uc8/training.jsonl alongside existing capture/ledger files.

## Independent qualification on Mac

Captured stock frames may have been corrected by the stock decoder. Therefore
records initially remain **training_eligible=false**. Never flip that flag just
because CRC, an address or a later packet agrees. Use the offline qualifier:

```sh
PYTHONPATH=src .venv/bin/python scripts/collection/qualify_far_training.py \
  /path/to/capture.tar --readsb /path/to/pinned/readsb-3.16.17 \
  --raw-root /path/to/adsb-neural-rescue/data/raw \
  --output /path/to/qualified/batch-training.jsonl.gz
```

It verifies checksums and original stock Beast/timestamp agreement, excludes all
reserved RF plus continuous RF in the same archive, and requires independent
uncorrected waveform decoding at the same timestamp. Neutral padding separates
short RF windows for the teacher; source times are mapped explicitly. Qualified
records use stock_crc_assisted format accepted by the existing fine-tuner, but
still require its ICAO, payload/IQ deduplication and RF-interval split guards.
It does not train/deploy or contact the receiver. Unconfirmed examples stay in
the immutable original archive. Updated verify.py/export_bursts.py support v3
while retaining v1/v2 compatibility where their original tools supported them.

## Verified offload

21 saved archives / 1,652,263,872 bytes were verified on Mac, then their precise
Pi copies were deleted. Mac destination:
`/Users/mit/Documents/!project/adsb-neural-rescue/data/raw/pi-offload-20261029`.
Both saved RF and saved CRC directories are empty at the recorded final audit.
New live capture RAM and existing decoder CRC RAM remain buffered for normal
saves. No forced CRC flush or decoder restart was performed. Nothing here
schedules ongoing future transfers.

The reusable task offloader takes only immutable capture-*.tar / batch-*.jsonl.gz
from explicit collection directories. It reuses a checksum-matched Mac backup via
hard link or downloads a new file, verifies size/hash, fsyncs backup files and
folders, then rechecks the exact Pi path, timestamp, size and hash before unlink.
No configs, graphs, active files, partial archives or directories are removed.

```sh
ADSB_NEURAL_DATA_ROOT=/absolute/path/to/adsb-neural-rescue \
  python scripts/collection/offload_20261029.py
```

## Validation and rollout

41 collection tests pass on Mac and Pi, plus 41 core Mac tests. They cover quotas,
restore, quality/causality rejection, gap/clock handling, SD bounds, exact archive
bytes and journal closure. A temporary real RF/stock qualification fixture uses
synthetic range metadata and is destroyed; it is not a real distant training
example. No qualifying distant stock track was present during live observation.

`tools/deploy_far_training.py` backs up sources/config in a root-owned directory,
cleanly stops only the collector, checks that the old RAM produced a saved file,
atomically installs, preserves the cap/save interval, and observes 90 seconds.
Startup/health failure restores prior files and restarts only capture. Protected
PIDs (except capture), decoder config/gain/switches and SDR sample counters pass.
This is an activation rollback, not an additional permanent watchdog. The existing
systemd Restart=on-failure policy remains unchanged.

For manual rollback, stop only adsb-far-capture; restore existed files/remove
newly added files according to files.json in the recorded backup directory;
then start adsb-far-capture. Do not restart readsb or the rescue decoder.

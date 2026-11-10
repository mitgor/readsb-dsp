# Daily ADS-B collection — 10 November 2026

**Transferred and verified six immutable saved archives (121,531,995 bytes, 121.5 MB), then removed only those exact checksum-verified Pi copies.** Mac backups and manifests were fsynced before remote identity, size, mtime, checksum and open-writer rechecks. Existing Mac data, receiver settings and active RAM buffers are preserved.

## Qualified distant data

The RF archive offered 272 stock-assisted windows. Independent uncorrected replay confirmed 130 at the same sample-clock transmission: 124 at 180–200 nm and 6 at 200–250 nm. The other 142 remain quarantined in the original archive. Original IQ/member hashes, Beast payload/time agreement, causal position age, NIC/NACp and non-MLAT/TIS-B guards passed.

New unique examples: 61 TRAIN, 55 VALIDATION and 14 fixed evaluation-only TEST. The existing incremental ledger now holds:

| Split pending since completed November 4 trial | Windows | Aircraft | UTC hours |
|---|---:|---:|---:|
| Train | 493 | 243 | 73 |
| Validation | 195 | 97 | 59 |

**Seven further qualified TRAIN windows are needed.** The 500-window threshold remains unchanged; validation and diversity thresholds are already met. No fitting on unchanged data, model deployment or repeated candidate benchmark occurred. Historical consumed-example statuses, fixed ICAO/payload/IQ groups and RF exclusions are retained. Cumulative fixed test coverage is 223 windows, including the 14 new ones.

Reserved 181 new continuous RF intervals globally as evaluation-only before label preparation. Verified and quarantined 4,929 CRC/IQ research windows from five saved CRC archives; these are not supervised labels.

## Current production baseline

All protected PIDs, method/model/library/source/config hashes, workers, gain and SDR loss/drop counters matched before/after this run. Observed enabled methods include energy, CRC research, timing, soft, matched, coherent, neural, Stream1090, pulse, sequence and acquisition. The running production command also exposes the Mac-helper mirror, whose activity was saved privately. These pre-existing settings were not activated or changed by this daily task. Future full-current-pipeline comparisons must include all enabled contributions rather than reuse the November 4 baseline.

The RF cap remains 5,000,000,000 bytes; normal 12-hour saves and all existing limits remain configured. No SDR or mirror consumer was opened, no capture flush was forced and no receiver/feeder service was restarted by this run.

## Transfer reconciliation

The original SSH/rsync transfer was unusually slow. Read-only downloads through the already configured LAN HTTP archive export assembled exact original archive bytes, with bounded range reads and full SHA-256 verification. One owned compressed prefetch and the redundant owned rsync were stopped; no receiver process was interrupted. Their partial files/initial receipt remain preserved and excluded from analysis. The resumed established safe offloader reused verified local backups, repeated exact remote safety checks and performed the final allowlisted deletions. Both manifests are reconciled without duplicate archive counting. This was transport recovery, not a decoder or collection failure.

Private source archives, labels, diagnostics, hashes and receipts are in data/raw/pi-offload-20261110, data/raw/prefetch-20261110 and results/daily-20261110. Only this aggregate report and reproducible scripts are public.

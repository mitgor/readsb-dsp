# Recent-data companion, 29 October 2026

Result: retain the live model set. The selected DSP-augmented companion improves
8 validation and 4 test packet-window reconstructions over the three-model neural
cascade, but adds **zero packets beyond the full current pipeline** on 40.65 RF
seconds. Mac/Pi accepted packet/timestamp signatures match. There are no baseline
losses. Pi additional inference CPU is 0.02173 CPU seconds per RF second, about
3.65% of baseline serial algorithm CPU. No deployment or live configuration change.

Both dated ONNX and PyTorch candidate weights are retained under
`models/candidates/recent-20261029/{raw,dsp}`. They are optional artifacts and are
not added to `PRODUCTION_COMPANIONS` or any automatic model-discovery path.

## Data and qualification

The private data workspace is the existing `adsb-neural-rescue` project. Set
`ADSB_NEURAL_DATA_ROOT` to its absolute path when running these scripts from
readsb-dsp. Use its existing Python environment with Torch/ONNX/NumPy/SciPy.
The source and transfer manifests identify exact snapshots; RF is deliberately
not committed. `common.py` resolves paths only; no script creates access,
changes collection, flushes a recorder, or alters the receiver.

Read the existing `scripts/learning/DSP_COLLECTION.md` in that data workspace.
Preparation assumes checksum-verified saved archives are already copied into
`data/raw/retrain-recent-20261029`, a frozen offline runtime snapshot under
`data/transfer/retrain-companion-20261029/runtime`, the old fixed NPZ splits under
`data/transfer/improvement-20261027/raw`, and their original dataset manifest.

- All 16,509 new CRC research windows remain quarantined. None had an exact
  same-transmission stock match within four microseconds. Later payload repeats
  or the same address do not authorize labels.
- Only closed, stream-complete continuous bursts qualify. Some archive-wide
  packet ledgers have missing closures; those open bursts/snippets are excluded.
- New labels require exact same-transmission live stock plus an independent
  zero-correction readsb DF17 decode on original RF, with validated sample clock
  and preamble-only alignment. Labels are stock-assisted, not physical truth.
- The no-fix teacher batches disjoint RF with neutral separators, records the
  sample mapping, and excludes one millisecond at both edges. No joining artifact
  supplies a supervised window. Aggregate identical-stock clock anchors verify
  short captures. `ADSB_LABEL_READSB` can specify the pinned 3.16.17 binary;
  the recorded run's executable SHA-256 is in `labels.json`.
- All prior `long-validation-*` reservations and evaluation-only RF are excluded.
  The latest entire archive is reserved before fitting. Original window holdouts
  remain unchanged; new aircraft follow compatible split buckets. Opposite-split
  RF overlaps and duplicate IQ/payloads are rejected.
- Qualification yielded 5,359 candidate windows, reduced to 3,355 new prepared
  windows: 2,615 train, 562 validation, 178 test. Only 8/1/0 have newly qualifying
  >=180 nm distances. Prior position NIC/NACp must be >=5, no MLAT, age <=15 s.
  Old unverified distance tags are not used for new far weighting.

## Frozen workflow

Commands are sequential except the two independent training variants, which may
run together. Output guards prevent overwriting completed fits/evaluations.

```sh
export ADSB_NEURAL_DATA_ROOT=/absolute/path/to/adsb-neural-rescue
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python scripts/learning/retrain_recent/prepare.py
python scripts/learning/retrain_recent/train.py --variant raw
python scripts/learning/retrain_recent/train.py --variant dsp
python scripts/learning/retrain_recent/freeze_candidate.py
python scripts/learning/retrain_recent/benchmark.py --output /new/path/mac-rf.json
python scripts/learning/retrain_recent/audit.py
python scripts/learning/retrain_recent/controls.py
python scripts/learning/retrain_recent/report.py
```

Both runs use a fixed seed, 1,000 updates, the previous best raw checkpoint,
noise/timing augmentation, synthetic replay, and preservation distillation.
New qualified far/hard windows receive extra sampling weight. The DSP variant
adds training-only fractional-timing/matched-IQ views. Selection is validation-only
(wrong CRC, new qualified far additions, overall additions, bit errors).
Neither test nor chronological RF chooses the checkpoint or variant.

The held-out RF replay includes energy, timing, soft, matched, coherent/pair retry,
all three production neural models, and Stream1090. Quarantined Broad CRC CPU is
included but its packets are excluded. Existing stock/unified output masks all
candidate additions. Mac Stream1090 uses the same functional CMake settings as
Pi (architecture-specific compiler flags differ). Frozen RF is evaluated once per
hardware, without tuning. Future replay of it is regression, not fresh validation.

Pi uses copied live libraries/models in owned tmpfs, nice19/core3/35% CPU/1 GiB/
900s. `pi_job.py` monitors established receiver health and stops only its own
process group on repeated failures. It never opens SDR or feeder output.
Temporary files may be removed only after a checksum-verified Mac copy; persistent
receiver archives and their 5 GB cap are untouched.

## Interpretation

The temporal RF holdout contains some previously seen aircraft/payloads; do not
call it aircraft-disjoint or post-freeze prospective RF. Prepared window splits
are ICAO/payload/IQ-disjoint. No new far test labels exist, so this run cannot
establish far-range generalization. Eight neural validation gains do not mean
eight new field packets. On this replay, the full baseline already covers them.

Each model passes 20,000 independent noise windows and clean no-overlap CRC
controls. The one non-target valid synthetic-overlap packet is exactly the known
secondary interferer, not an unaccounted codeword. Export packet/bit parity passes.
Candidates nevertheless remain offline because no full-pipeline benefit emerged.

The Mac source snapshot needs several missing offline build dependencies from
the repository; all are separately hashed in `supplemented-offline-sources.json`.
Actual Pi replay uses copied live native libraries. Its accepted packets match
Mac exactly. Serial replay CPU excludes live transport and is not electric power.

# Larger companion, November 10

Private, additive architecture comparison and explicitly authorized activation of the previously validated November 10 tiny companion. See ../../validation/larger-companion-20261110/report.md.

Set ADSB_NEURAL_DATA_ROOT to the private workspace and use the established project Python environment. The original retrain-20261110 prepared dataset, runtime snapshot, interval reservations and qualification audits are required. Never rebuild or overwrite those holdouts from this experiment.

Workflow: train.py for raw and DSP variants, freeze.py for validation-only selection, controls.py, benchmark.py for selected raw and secondary DSP (explicit --variant), then isolated target staging using pi_prepare.py and pi_run.py. Read each script's arguments before use. Dated outputs are frozen evidence: use a new experiment directory for another trial. report.py regenerates only aggregate public reports.

activate.py is a one-shot receiver controller with persisted ownership checks and backups, not an installer. Do not rerun activation casually. Existing activation backup: /var/lib/adsb-companion-20261110-v2. Manual rollback on the receiver: sudo python3 /var/lib/adsb-companion-20261110-v2/activate.py --rollback. It restores the original cascade/runtime and restarts the coordinator only; it refuses to overwrite source modified by someone else.

The larger networks were not deployed. Raw RF, model weights and receiver snapshots remain private.

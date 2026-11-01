# Stock-only FR24 test ended early — observed 1 November 2026

The durable extended-result.json records the stock-only trial aborted on an SDR loss/drop guard and closed at2026-10-31 10:52:12Europe/Berlin. Its completed flag is false. The planned1November20:00end was not reached. This is the active v2 monitor's real abort, distinct from the previously documented intentional v1 monitor handovers.

Readsb's cumulative samples_lost counter changed from0to262144(~0.109RF seconds at2.4Msps), samples_dropped remains0. This does not identify the cause of that past sample loss or prove the cause of the October27cloud-count collapse. No further counter increase was observed during today's collection run.

Restoration receipts show automatic return to127.0.0.1:31005, DSP intent and routing guard active. Current direct inspection confirms combined input, connected FR24, reader connected, ring not full, valid timing and active normal feed-guard timer. Readsb/DSP/relay/collector PIDs are unchanged; only the feeder restarted as part of restoration. The RAM extended-status file still says aborted_restoring; the durable result additionally records the completed restoration and closed timestamp.

Do not call this a completed60hour stock-only comparison. Use only fully contained verified stock-only hours before the abort for cloud analysis; compare current combined hours separately. No conclusion about cloud recovery was made by the daily learning workflow. That workflow did not restart/extend the trial, change routing, switches, gain, models, services or collector limits.

Private binary evidence: private/stock-trial-abort-20261101/closed-trial.tar plus checksum receipt, original monitor scripts/result/state/hourly logs/schedule and current read-only observations. Future scheduled review should account for this early closure. Existing independent deadline timers were left unchanged.

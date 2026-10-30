# October 27 incident cause review

Read-only reconstruction from archived activation/status records, Git changes,
FR24 charts already extracted through the signed-in UI, current historical RRDs
and incident-era configuration backups. The running twelve-hour stock trial is
preserved; no new condition is launched and no support message sent.

Run `analyze.py --data-root PRIVATE_WORKSPACE --output DATED_OUTPUT`, then
`report.py --output DATED_OUTPUT`. `collect_rrd.py` runs on the established Pi
through SSH and only reads named RRD files; redirect its JSON to the private
workspace `results/fr24-oct27-cause-20261030/rrd-history.json`.

Raw RRD data, full credentials/config archives and binary journals stay in the
private incident workspace. Published configuration comparisons contain key names
and equality checks, never the sharing key. Ratios compare different counter
semantics and are indices of change, not packet delivery/loss probabilities.

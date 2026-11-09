# Controls and CPU repair — 9 November 2026

Two causes: the controls service retained an old in-memory capture validator
since October 29; asynchronous Stream1090 completion discarded the child CPU
returned by the decoder. Current capture configuration itself is valid.

The additive async engine now receives MethodMetrics and calls record_external
once per completed future, even for discarded old epochs. Grouped statistics do
not charge it again. The table's total, shares, CPU/extra and relative cost include
the child. Python coordinator overhead remains unassigned, as documented.

Current `web_control.py` gets a no-op fast path so unchanged Apply preserves exact
configuration bytes and rollback ownership. The deployed version retains its
Stream1090 executable check and socket timeout additions. Restarting the API
service loads current source without changing the RF policy. The API response is
not masked and fixed-policy validation is not relaxed.

`deploy.py` stages exact before/after backups, verifies live profile/source and
CRC save headroom, installs an independent finite guard-resume timer, pauses the
profile check during coordinator initialization, and restores/resumes checks in a
finally block. Restart only controls and coordinator. readsb, FR24, relay, ADSBx
and far collector keep their PIDs. No flush/delete/config-switch operation.
On failure, restore the prior source and manifest, then restart those same two
services. Completed captures and the collector's active RAM stay untouched.

`test_accounting.py`: three targeted tests passed on Mac and Pi. HTTP GET and
same-origin no-op POST both return 200, with unchanged settings revision. Two
live metric samples show positive/increasing CPU equal to the engine audit.
`record.py` verifies/fsyncs private before/after evidence and publishes redacted
results. Private workspace results/async-dashboard-fix-20261109 is immutable per
run; use new paths for subsequent runs.

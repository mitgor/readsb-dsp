# Rust coherent and acquisition reactivation — 9 November 2026

Rust ordinary coherent, paired coherent and acquisition scoring/selection are active. Both coherent workers map the installed Rust libraries. Gain remains 38.6 dB. Only the DSP coordinator was restarted; readsb, FR24, the relay, ADS-B Exchange and the RF collector retained their PIDs. Neural models, switches and feeder routing were preserved. EM was not changed.

## Why the previous release rolled back

At 30 October 00:19:35 CET, two legacy watchdogs restored C after three failures of an assertion that aligned RF seconds must advance. The recorded reason was `watchdog: AssertionError('DSP RF processing stalled')`. That assertion did not distinguish input silence, alignment inactivity and computation failure. Both guards could restore/restart concurrently. No Rust panic or segmentation fault was found in the preserved service records. The underlying cause cannot be established; neither a Rust defect nor a false alarm is proven. Preserved binary journal SHA-256: `dd2f1e9dcd8f49277a164cbc33776a62c901f087b69f7058b0010af5b41dea38`.

## Pi validation

| Check | Result |
|---|---|
| Coherent recorded windows | 3,269; every output array bit-exact against C |
| Coherent augmentation | 8,192 phase/amplitude cases and 500 peak cases per branch |
| Acquisition | 1,201 scoring/selection cases; budgets 1/8/16/64/256; tie fallback and noise controls |
| Full enabled native pipeline | 24 RF seconds, six Rust cycles; all raw candidates, guarded events, decisions and alignment audits identical |
| Persistent-worker soak | 315.7 seconds wall; 144 RF seconds |
| Live observation | 305.2 seconds; healthy guard, unchanged protected services/configurations/sample-loss counters |
| Rollback/policy tests | Seven tests passed on Mac and Pi; exact C restoration, coordinator-only restart, human edits preserved |

| Kernel | CPU reduction versus C |
|---|---:|
| Ordinary coherent | 11.85% |
| Paired coherent | 9.82% |
| Acquisition, budget 16 | 13.38% |

These are isolated kernel savings, not whole-Pi savings. Full worker CPU changed by -1.01% in this finite replay; one C cycle versus six Rust cycles makes that descriptive rather than a precise system energy estimate. The 24 seconds are historical regression RF, not fresh range evidence. This is a parity deployment, not a claim of additional detections. Unmodified Stream1090 retains original-first output.

Live observation produced 991 coherent and 215 acquisition extras while stock forwarding continued. These are production counter increments, not evidence of an advantage over C. Processing proxy ranged 1.188–1.255 seconds, below the 3-second limit. Collector cap remains 5,000,000,000 bytes; no persistent archive deletion or forced recorder flush occurred.

## Rollback and evidence

One coordinated persistent guard replaces the competing legacy Rust guards and temporarily owns the prior async profile guard's safety checks. It distinguishes RF-input, worker-completion and alignment progress, records failure snapshots, checks actual mapped libraries and rolls back after repeated unsafe conditions. Alignment inactivity with healthy input/work is an advisory. The guard also checks processing budget, sample loss, relay, FR24, collection and queues. It respects unexpected human changes instead of overwriting them. The old rollback records remain intact, with successor pointers.

Status: `sudo python3 /var/lib/adsb-rust-kernels-20261109/control.py status`

Manual rollback: `sudo python3 /var/lib/adsb-rust-kernels-20261109/control.py rollback`

Complete isolated source/model/RF/results bundle and deployed C rollback bytes, live observations, units and journals are checksum-verified and fsynced on the Mac in the private results directory. Public summary contains no raw RF, sharing keys or credentials. Receipt hashes and reproducible scripts are retained. Stability evidence is finite; the persistent guard remains enabled.

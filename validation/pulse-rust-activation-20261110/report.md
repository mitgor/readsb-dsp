# Rust pulse-discriminant production activation — November 10, 2026

Rust pulse filter is active in both DSP workers, with exact installed-inode checks and backend marker `rust-1.99.1/pulse-discriminant`. The deployment uses the exact library that passed bit-exact optimized-C/actual-C and complete-pipeline replay checks. Other C helpers and all existing Rust kernels remain unchanged.

Only the DSP coordinator was briefly restarted to load the new library. Readsb, FR24, the relay, ADS-B Exchange and the RF collector retained their PIDs and kept running. The existing 38.6 dB gain, method/worker configuration, routing, neural models and 5,000,000,000-byte RF cap were preserved. Normal clean coordinator shutdown had ample archive headroom; no forced recorder flush or persistent archive deletion.

The 304.1-second live observation passed. It processed 280 aligned native RF seconds and 297 Stream RF seconds; forwarded 768,927 stock bytes, 1,567 DSP extras including 22 pulse extras. These counts establish forwarding activity, not extra recovery versus C. No new sample-loss/drop counters. Processing proxy ranged 0.971–2.306 seconds, below the three-second limit.

A persistent five-second guard checks actual Rust mappings, owned file hashes, processing progress/margin, queues, temperature and receiver/relay/FR24/collector health. Repeated unsafe conditions restore the exact original C pulse library bytes, then restart only the DSP coordinator. Unexpected human file edits are preserved. Systemd provides an activation-failure fallback. Coordinator checks/restores share the older coherent/acquisition guard's lock to prevent overlapping restarts; its timer and state are retained, and Stream monitoring continues.

Two rollback tests passed: exact C-library restoration with coordinator-only restart, and preservation of external human changes. Original rollback bytes, deployed code/library, dependencies, units, model verification, live observations and journals are checksum-verified/fsynced on the Mac. The pulse model matches the target parity-test archive.

Target validation measured about 6% more pulse-batch CPU than C, with identical packet output. This is a small component; the one-pass full-worker timing difference is not a precise total-CPU result. This activation follows the user's explicit request and makes no CPU/energy/range improvement claim. Finite live validation is supported by the persistent rollback guard.

Status: `sudo python3 /var/lib/adsb-pulse-rust-20261110/control.py status`

Manual rollback: `sudo python3 /var/lib/adsb-pulse-rust-20261110/control.py rollback`

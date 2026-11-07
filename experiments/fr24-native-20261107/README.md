# Official FR24 DVB-T comparison — 7 November 2026

Current active attempt: **v4**. The official ARM64 stable apt repository was
refreshed successfully and offered FR24 1.0.57-1, already installed. FR24's normal
DVB-T launcher selects installed dump1090-mutability 1.15; no newer alternative
was substituted for the official stock baseline.

Measured UTC interval: November7 12:00 through November9 12:00 (48h), i.e.
13:00–13:00 Europe/Berlin. Startup/failed-attempt periods are excluded.

`trial.py` is deployed root-only under
`/var/lib/adsb-fr24-native-20261107-v4`. Restore with its `--restore` action.
The primary restoration and independent safety timers expire at the deadline
and ten minutes later. A once/minute health timer rolls back on a decoder,
feeder, configuration or paused-service fault. The app review is scheduled for
November9 13:20Berlin; it must compare actual cloud hours rather than infer
improvement from local counters.

- Device0, PPM0, fixed38.6dB. Native tuner reports38.60dB.
- Existing receiver location/max-range450 preserved. FR24 MLAT remains off.
- A logging-only shell wrapper execs the unmodified official-selected decoder;
  it captures stderr/gain without changing packets.
- Readsb is stopped; a temporary condition prevents dependency auto-start and
  dual SDR ownership. The stock decoder alone owns the USB device.
- DSP and far RF collector cgroups are frozen, preserving their PIDs and live
  RAM buffers. No forced archive flush, no archive deletion, no5GB-cap change.
  New training RF is unavailable during this hardware test. Power loss still
  loses volatile RAM as it ordinarily would.
- The existing relay reconnects to stock Beast30005 and supplies other feeders.
  FR24 takes raw data directly from its own child, bypassing the DSP relay.
- A temporary runtime bridge keeps the existing map/graphs JSON endpoint fresh.
- Original configs/drop-ins, guard/graph timers and original receiver are
  restored; frozen buffers resume. Installation, restore and failure histories
  are saved privately because original config backups contain the sharing key.

Earlier attempts: long procargs parsed by standalone dump1090 but caused invalid
arguments when launched through FR24. A no-SDR preflight left a net-only child;
only that verified owned child was terminated. Short normal launch args started
correctly; a stale error log then caused an unnecessary rollback. V4 clears and
preserves the previous log, accepts only fresh errors, and passes the added
regression test. An isolated dummy argv probe did not launch its fake decoder
and is inconclusive. All attempts are preserved; none is counted as exposure.

Six tests cover config/gain preservation, refusing unexpected runtime paths,
actual restore ordering/buffer thaw, and rejecting stale startup errors. Actual
failure rollbacks also restored original reception and preserved paused PIDs.
These tests do not establish cloud improvement; that result remains pending.

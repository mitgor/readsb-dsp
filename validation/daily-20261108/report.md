# Daily ADS-B collection — 8 November 2026

No new saved archives are available. The ongoing native FR24 test deliberately freezes DSP and far-RF collection through 9 November at 13:00 Europe/Berlin, preserving their RAM buffers. Both cgroup freeze flags are 1, consistent with the documented test. FR24 and its dump1090-mutability decoder are running.

No data was deleted or transferred, no services/configuration/routing were changed, and no flush was forced. The 5,000,000,000-byte RF cap remains configured.

The unchanged ledger retains 417 qualified TRAIN windows and 139 VALIDATION windows since the last completed November 4 training trial. Another 83 TRAIN windows are needed. No training or repeat evaluation was run. Previous consumed examples and all evaluation reservations remain protected.

The initial readsb-specific snapshot failed on a statistics field omitted by the native decoder. This is a diagnostic-schema mismatch, not a receiver failure. The failed empty output, read-only diagnostics and corrected observation are preserved privately. Daily collection will retry on its next normal run; it must not interrupt the native test.

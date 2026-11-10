# readsb-dsp web branding, 10 November 2026

Canonical receiver URL: `/readsb-dsp/`. Existing `/neural-rescue/` aliases remain
available for bookmarks, scheduled offload jobs and archived reports. The physical
web root is exposed through `/usr/share/readsb-dsp -> /usr/share/adsb-rescue`;
no RF archives, runtime directories, model paths or production services moved.

`migrate.py` is the dated, receiver-specific migration, not a generic installer.
It validates the expected control-handler source, preserves exact originals under
`/var/backups/readsb-dsp-web-20261110`, adds canonical lighttpd mappings, updates
absolute HTML links and the main dashboard title, restarts only the web controls,
and reloads lighttpd. Failure restores the saved web files and mappings. It refuses
a second run over its backup. The new-installation example is instead
`packaging/lighttpd-readsb-dsp.conf`.

Verified HTTP 200/JSON for new status, settings, feed and capture URLs, reception
map and legacy settings. All six protected process IDs remained unchanged:
readsb, FR24, DSP coordinator, relay, ADS-B Exchange and RF collector. Relay stock
connection remained healthy. Exact local evidence is kept in the private data
workspace under `results/web-branding-20261110/result.json`.

Validation: 43 integrated tests plus the canonical/legacy control-path regression;
clean native-library build and all three frozen model hash checks passed on Mac.
Systemd parsed all four generated unit files on the receiver; executable checks
correctly report the uninstalled `/opt/readsb-dsp` paths. No fresh receiver was
installed or activated as part of the web migration. Installer CI smoke checks
are added; a complete fresh-OS install remains a release qualification step.

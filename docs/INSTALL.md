# Install readsb-dsp

Supported target: Debian 12+ or 64-bit Raspberry Pi OS, Python 3.11+, systemd,
RTL-SDR USB receiver. Start with a fresh OS or explicitly stop the existing SDR
owner during a planned migration. Never run two processes against the same SDR.
No feeder account, sharing key, receiver location or RF data is shipped.

## 1. Dependencies and installation

```sh
sudo apt-get update
sudo apt-get install -y git build-essential pkg-config python3-venv python3-dev \
  libncurses-dev zlib1g-dev libzstd-dev librtlsdr-dev libusb-1.0-0-dev
sudo usermod -a -G plugdev "$USER"
git clone https://github.com/mitgor/readsb-dsp.git
cd readsb-dsp
# Replace all three values with your own coordinates and gain in dB:
sudo python3 tools/install.py --lat YOUR_LAT --lon YOUR_LON --gain YOUR_GAIN
```

The installer exports tracked source to `/opt/readsb-dsp`, creates a private venv,
builds readsb with RTL-SDR and the native C kernels, verifies the frozen neural
model hashes, and installs four **inactive** services. It refuses an existing
installation rather than overwriting it. It does not stop or start receivers,
modify feeder settings, download RF or enable experimental recording. Package
installation requires Internet access for Python dependencies. Keep the checkout
at a reviewed commit. A bare `pip install` wheel is not a full receiver install;
the source tree, models and native builds are required.

For a preview without root or changes to system services:

```sh
python3 tools/install.py --lat 52 --lon 13 --gain 38.6 --render-only /tmp/readsb-dsp-units
```

## 2. Activate on the intended receiver

First identify and stop your previous SDR-owning service if one exists. Record
its name and settings for rollback. The installer intentionally does not guess it.
Verify librtlsdr's udev rules grant the `plugdev` group access to the receiver;
if the DVB kernel driver owns it, follow your distribution's RTL-SDR setup.

```sh
sudo systemctl enable --now readsb-dsp-decoder readsb-dsp-receiver \
  readsb-dsp-relay readsb-dsp-dashboard
systemctl status readsb-dsp-{decoder,receiver,relay,dashboard} --no-pager
journalctl -u readsb-dsp-decoder -n 50 --no-pager
curl http://127.0.0.1:8912/api/status
```

`/etc/readsb-dsp/` contains methods, worker and CPU-budget configuration.
`/run/readsb-dsp/` contains ephemeral status, I/Q socket and relay outbox.
`/var/lib/readsb-dsp/` is reserved for optional logs (disabled in supplied units).
Runtime directory preservation lets independent services restart without deleting
the shared socket directory. Configuration changes to methods/workers require a
**decoder** restart; CPU-budget updates are read dynamically. Never enable
readsb's separate `--dsp-rescue` mode simultaneously with these workers.

The default coordinator (`rescue.async_shadow`) publishes worker completions
independently to `rescue.async_feed`. [Transport policy and rollback](ASYNC_OUTPUT.md)
describe the five-second transmission cache and preserved acceptance checks.

Stock Beast: `127.0.0.1:30005`. Guarded combined Beast: `127.0.0.1:31005`.
After verifying stock reception and healthy decoder/relay status, explicitly
configure your existing FR24 or ADS-B Exchange feeder to consume the combined
port if desired. The installer neither installs proprietary feeders nor edits
credentials. Local extras are not a guarantee of cloud-credited hits.

## 3. Dashboard and web prefix

The CPU-budget dashboard binds loopback `http://127.0.0.1:8912/`.
The supplied [lighttpd example](../packaging/lighttpd-readsb-dsp.conf) serves it at
`http://RECEIVER/readsb-dsp/`. Install lighttpd, enable `mod_proxy` and `mod_redirect`,
copy the example to `conf-available`, enable it, validate `lighttpd -tt -f
/etc/lighttpd/lighttpd.conf`, then reload. This is a trusted-LAN interface, with
same-origin/revision-checked budget writes, not an Internet administration portal.

Existing full statistics dashboards use the same canonical `/readsb-dsp/` prefix.
The migration helper retains `/neural-rescue/` aliases (including archive/API
URLs) to avoid breaking scheduled jobs and saved bookmarks. Physical production
runtime/archive directories and service names remain unchanged: renaming them
would unnecessarily invalidate watchdogs and collection manifests. Historical
reports and private evidence retain their original names.

## Included release versus experimental receiver

| Component | Installer |
|---|---|
| Pinned readsb + nonblocking I/Q tap | Included, sole SDR owner |
| Energy, timing, soft, matched, coherent, frozen neural cascade | Included |
| Pulse/sequence/acquisition | Included opt-in; shipped method defaults retained |
| CPU admission governor and budget dashboard | Included |
| Guarded asynchronous stock + extras relay | Included by default; no intentional stock holdback |
| Standalone Stream1090 / latest Rust deployment overlays | Dated experiments; not promoted into this installer |
| Research capture, far-range map, private historical reports | Not enabled or bundled with private data |
| RF recording / neural retraining | Not enabled by installation |

Do not apply dated experiment deployment scripts to an unrelated receiver: some
are tied to the private test receiver's hashes, service names and paths. The
installer does not claim equivalence to that receiver's current configuration.

## Rollback and upgrades

To revert, first point feeders back to the original stock source. Stop/disable
all four `readsb-dsp-*` services, then restore your prior SDR owner. Never start
it before stopping `readsb-dsp-receiver`. Preserve `/var/lib/readsb-dsp` and any
configuration backups. Nothing replaced `/usr/bin/readsb` or your old services.

Upgrades are deliberately not in-place: review changes, preserve configurations,
validate an isolated build, and plan activation. Do not delete a working install
just to bypass the installer's existing-path check. Failure leaves staged files
for inspection and never starts partial services.

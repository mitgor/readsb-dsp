# deadsb dsp · readsb-dsp

An integrated, experimental ADS-B receiver distribution: **readsb + energy/DSP +
neural rescue + dashboard + offline benchmarks**, with adaptive rescue CPU
budgeting. This is an independent GPL-3.0-or-later project, not an endorsed
upstream readsb release.

The repository is **[mitgor/readsb-dsp](https://github.com/mitgor/readsb-dsp)**.
The project/product name is **deadsb dsp**. The original DSP-only patch package,
release history and reproducible preparation helper are retained; see
[the legacy guide](docs/LEGACY_PACKAGE.md).

## What's included

| Component | Location | Purpose |
|---|---|---|
| Complete pinned readsb fork | `readsb/` | Primary decoder, optional native DSP-only rescue and nonblocking I/Q tap |
| Native shared frontend and workers | `src/rescue/` | Energy, timing, weak-bit repair, matched/coherent filtering, optional neural cascade |
| CPU governor | `src/deadsb/governor.py` | Total system utilization feedback; reduce optional work under load |
| Loopback dashboard | `deadsb dashboard` | CPU target, admission profile, per-method reception/CPU and distance statistics |
| Offline benchmark | `deadsb benchmark` | Reproducible UC8 replay, packet digest and CPU cost, no network output |
| Native stock/DSP controls | `readsb/tests/dsp-rescue/` | Stock preservation, boundaries, noise and sanitizer checks |

Readsb is based on 3.16.18 / upstream commit `9460652`, plus our prepared native
integration and nonblocking tap. [Provenance](docs/INTEGRATION_PROVENANCE.json)
records exact source commits and imported runtime/model hashes. No private RF,
receiver coordinates, feeder sharing keys or installed configuration are bundled.

## Build locally

Python 3.11+, a C compiler, make, zstd, zlib and ncurses development headers are
required. RTL-SDR builds also need librtlsdr and libusb development packages.

```sh
git clone https://github.com/mitgor/readsb-dsp.git
cd readsb-dsp
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/deadsb build                 # native libraries + file-only readsb
# .venv/bin/deadsb build --rtlsdr      # helper cleans only its own decoder build first
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
make -C readsb test dsp-rescue-test dsp-rescue-test-sanitize
```

Builds do not install binaries, open the SDR or change receiver services. The
existing receiver keeps running its existing installation. Copying these files
onto a receiver does not enable the new governor.

## 60% CPU target

The supplied policy targets **55% total system CPU over 30 seconds**, with a
**60% ceiling used for stronger shedding**. It samples Linux `/proc/stat`, not
load average. Four cores at 60% mean 2.4 CPU-seconds per wall second, including
stock decoding, feeders and unrelated processes.

| Profile | Rescue admission |
|---|---|
| Full | Operator-configured methods and existing budgets |
| Bounded | Halved neural/coherent candidate budgets; pair, sequence and acquisition retries suspended |
| Cheap | Energy + configured timing/soft/matched; neural/coherent and research work suspended |
| Energy | Additional energy slicing only |
| Stock-only | No rescue decoding; primary readsb continues independently |

The governor can only reduce already configured methods. It changes job admission
at RF-second boundaries; it never changes thresholds, CRC/identity guards, model
weights, feeder routing, gain or collection limits. It reduces work every five
seconds under pressure and restores one profile after 60 seconds of cool,
low-CPU operation. Stale/invalid telemetry, severe backlog or heat suppress rescue.
The shared frontend producer/consumer lifecycle remains bounded at every level.

**This is a cooperative target, not a guaranteed system-wide cap.** Stock and
unrelated work are never throttled. Short spikes and a stock-only baseline above
60% can exceed the target. Shedding work can lose rescue extras; it does not
replace or discard stock output. Profile ordering is a conservative policy, not
proof of the most efficient bundle. Independent ablation benchmarks are required
before claiming optimal recovery per CPU second.

## Full receiver mode

Use one stock-first readsb process with the I/Q tap and separate rescue workers.
Readsb's optional in-process `--dsp-rescue` must remain **off** in this mode to
avoid doing the same DSP twice. The native-only mode is an alternative for simpler
receivers; its cooperative microsecond budget is documented separately in
[the native guide](docs/NATIVE_DSP_RESCUE.md).

The tap is inactive unless the readsb process is explicitly started with
`ADSB_RESCUE_SOCKET=/run/deadsb/iq.sock`. Readsb remains the sole SDR owner. Rescue
input and output use separate sockets; no candidate output is automatically sent
to a feeder. A manual deployment profile is in [the integration guide](docs/DEADSB.md).
It deliberately requires the operator's receiver location and established output
routing. Existing stock-only and guarded-union outputs can serve FR24 and ADS-B
Exchange; unverified research branches stay quarantined.

```sh
# After setting up a dedicated runtime and supplying your own receiver location:
deadsb shadow --root "$PWD" --runtime /run/deadsb --archive /var/lib/deadsb \
  --lat YOUR_LAT --lon YOUR_LON --config config/methods.json \
  --worker-config config/workers.json --cpu-budget-config config/cpu-budget.json \
  --no-logging
# Separate terminal; binds only 127.0.0.1, no receiver/service control:
deadsb dashboard --runtime /run/deadsb --budget-config config/cpu-budget.json
```

The new dashboard is `http://127.0.0.1:8912/`. It distinguishes configured methods
from current admission and reports CPU cost per attributed additional packet.
Shared costs and attribution do not establish causal marginal benefit or power.
This interface changes only budget settings; method configuration is explicit in
`config/methods.json` and requires a rescue worker restart to reload.

## Benchmark without touching the receiver

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 deadsb benchmark \
  --iq /path/to/recording.uc8 --output /tmp/deadsb-full.json --profile 0
# A separate, fresh output for an explicitly reduced policy:
deadsb benchmark --iq /path/to/recording.uc8 --output /tmp/deadsb-cheap.json --profile 2
```

UC8 input must be 2.4 MS/s and start at the native resampler's phase-zero origin.
Use sample-index reservations and aligned crops for RF from a continuous receiver.
Reports contain aggregate candidate counts, RF hash, packet digest and CPU cost;
raw candidates are **not** verified additional transmissions. Distance and gains
beyond stock/actual production require synchronized stock, accepted-DSP and
position ledgers. Do not tune against held-out RF or train on unverified outputs.

## Status and limits

This source integration is being validated independently of the working receiver.
The 60% policy has simulation and isolated replay tests; it does not yet have a
sustained live overload/thermal qualification. No automatic deployment, new RF
capture or feeder restart is performed by any build/benchmark command.
Read [validation](validation/DEADSB.md) for the current evidence and limitations.

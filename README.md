# readsb DSP rescue

An independent, experimental **source add-on package** for
[wiedehopf/readsb](https://github.com/wiedehopf/readsb). It adds native C energy
slicing, fractional timing retries, bounded weak-bit repair and complex matched
filtering. **No neural models or inference runtime.**

This is not an upstream readsb release or an endorsed extension. The maintainer
is not seeking demodulator additions; [PR #163](https://github.com/wiedehopf/readsb/pull/163)
remains available for discussion/visibility. Development of this add-on continues
here independently.

## Status

- Feature **off by default**. `--dsp-rescue` enables **shadow mode**: stock output
  only, with rescue counters. A separate flag opts in to additional output.
- UC8 at 2.4MS/s, **RTL-SDR and file input only**. Other SDRs/formats are rejected.
- Source package pinned to readsb **3.16.18**, commit
  `9460652952a62fcfd9bf11a2664d737147f266a5`. It is not a universal patch for
  arbitrary versions. No precompiled binaries or service installer are provided.
- Native macOS builds/replays pass; actual native Pi 4/RTL-SDR profiling remains
  outstanding. Existing offline kernels were tested on Pi, which does not validate
  this native live integration's performance.

## Prepare an isolated build

On Debian/Raspberry Pi OS, install build dependencies if needed:

```sh
sudo apt update
sudo apt install git build-essential pkg-config libncurses-dev zlib1g-dev \
  libzstd-dev librtlsdr-dev libusb-1.0-0-dev
```

Python 3 is used by the preparation helper only; the native decoder has no Python
runtime requirement. On macOS, use Xcode command line tools and Homebrew `zstd`,
`pkg-config` and `librtlsdr` for the equivalent build.

```sh
git clone https://github.com/mitgor/readsb-dsp-rescue.git
cd readsb-dsp-rescue
python3 tools/prepare.py build/readsb --build --rtlsdr --jobs 2
```

The helper verifies patch hashes, clones the pinned upstream source into a **new**
directory, applies both patches, verifies the exact resulting source tree, and
optionally compiles it. It refuses an existing destination. It leaves the patches
staged in the new source checkout. It never installs a binary, runs sudo, restarts
services, changes feeder settings or opens the SDR. `--source /path/to/local/readsb`
can use an existing clone as a read-only source; its pinned base must be present.
Omit `--rtlsdr` for a file-only build.

The same patches can be applied manually to a clean pinned source tree, in order:

```sh
git apply --check /path/to/readsb-dsp-rescue/patches/0001-contrib-dsp-rescue.patch
git apply /path/to/readsb-dsp-rescue/patches/0001-contrib-dsp-rescue.patch
git apply --check /path/to/readsb-dsp-rescue/patches/0002-native-dsp-rescue.patch
git apply /path/to/readsb-dsp-rescue/patches/0002-native-dsp-rescue.patch
```

## Test with a recording first

Use a UC8 I/Q recording at exactly 2.4MS/s; no private recordings are distributed.
These commands have no network outputs and do not access a physical receiver:

```sh
cd build/readsb
# Stock output plus shadow rescue counters on stderr
./readsb --device-type ifile --ifile /path/to/capture.uc8 --iformat UC8 \
  --raw --mlat --dsp-rescue > stock.txt 2> rescue-summary.txt

# Explicit experimental union output, still only a local file
./readsb --device-type ifile --ifile /path/to/capture.uc8 --iformat UC8 \
  --raw --mlat --dsp-rescue --dsp-rescue-output > union.txt 2> union-summary.txt
```

Add `--throttle` to pace file input at its original RF rate. Rescue summary arrays
`raw` and `extras` are ordered **energy, timing, soft, matched**. `extras` is the
count of deduplicated guarded additions; `forwarded` is actual native submissions.
Stock's ifile path currently exits 1 at EOF; inspect the output and summary rather
than using that exit status alone as a success/failure test.

For an eventual live trial, keep the installed receiver configuration backed up,
profile a separate shadow build first, and never run two processes against the
same SDR. Merely building this package does not affect the working receiver.
The native output flag feeds the existing readsb output path, so existing network
settings would determine where additions go. No live deployment is automated.

## Recovery and safeguards

Stock demodulation runs first, then bounded cooperative DSP work on the existing
decode thread. There are no new worker threads. Live FIFO backlog skips rescue
work, and default wall budgets cap it at min(5ms, 10% of each buffer's RF duration).
This is not a hard realtime guarantee; slower hardware can lose rescue coverage.

The UC8 tap preserves shared sample timing and packet/FIR context across buffers.
Candidates wait for the next stock pass, require valid DF17 CRC and prior
uncorrected stock ICAO identity within 30 seconds, and pass transmission duplicate
and same-time conflict checks. Additions cannot establish later identity.
Weak-bit repair preserves DF/CA/ICAO bits, tests at most 21 hypotheses, and honors
`--no-fix`. There is no broad CRC search, relaxed header search or interference
cancellation. See [native design and limits](docs/NATIVE_DSP_RESCUE.md).

## Evidence and limitations

On **one 10-second recording**, local-file output preserved all **6,272 stock
records** and added **70 guarded DF17** on top of 1,403 stock DF17 (about 5%).
Disabled/shadow output preserved stock timestamp/payload pairs. A paced shadow
run found 61 additions under its budget, demonstrating scheduling sensitivity.
These are CRC/identity-guarded candidates, **not independent RF truth**, a general
range improvement, or an established false-positive rate.

Eleven synthetic boundary packets were counted once; generated noise (0.2s) and
shuffled real I/Q (10s) produced zero raw rescue candidates. Standard CRC/CPR,
14 offline reference tests and native ASan/UBSan tests passed on macOS arm64.
Aggregate reports are in [validation/](validation/). No receiver coordinates,
credentials, private captures or per-aircraft candidate logs are included.

```sh
make -C build/readsb test
make -C build/readsb dsp-rescue-test
make -C build/readsb dsp-rescue-test-sanitize
```

More replay controls and optional NumPy/SciPy reference checks are described in
[testing notes](docs/TESTING.md). Hardware shadow profiling, sustained overload,
sample-gap/thermal tests and longer independent noise/receiver controls remain
necessary before relying on live extra output.

## Package contents and license

`patches/0001-*` contains the optional offline reference; `patches/0002-*` adds
native integration. `manifest.json` records the base, patch hashes and resulting
Git tree. `tools/prepare.py` reproduces that tree without modifying the source
clone or installed receiver.

GPL-3.0-or-later. Upstream copyright/license notices are preserved in the patches,
[LICENSE](LICENSE) and [COPYING](COPYING). See individual source files for notices.

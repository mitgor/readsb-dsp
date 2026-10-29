#!/bin/bash
set -euo pipefail
TASK_ROOT="$PWD"
python3 - <<'PY'
import hashlib
from pathlib import Path
for name,expected in [('rustc.tar.xz','acdcdfe09ae1f103aa9a2b7f88903a9588bc2e99288af10e6fbf5514e2e49f25'),('rust-std.tar.xz','e25668477083d6a9ddb87b9beb9c00742225f38233ccb4bfba3afa7a07427f52')]:assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected
PY
mkdir -p toolchain
tar -xJf rustc.tar.xz --strip-components=2 -C toolchain rustc-1.99.1-aarch64-unknown-linux-gnu/rustc
tar -xJf rust-std.tar.xz --strip-components=2 -C toolchain rust-std-1.99.1-aarch64-unknown-linux-gnu/rust-std-aarch64-unknown-linux-gnu
/home/pi/adsb-neural-rescue/.venv/bin/python experiments/rust-acquisition/build.py --rustc "$TASK_ROOT/toolchain/bin/rustc"
/home/pi/adsb-neural-rescue/.venv/bin/python experiments/rust-acquisition/controls.py --work experiments/rust-acquisition/.work --decoder-root /home/pi/adsb-neural-rescue --output pi-controls.json
/home/pi/adsb-neural-rescue/.venv/bin/python experiments/rust-acquisition/benchmark.py --output pi.json

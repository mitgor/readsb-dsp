#!/bin/bash
set -euo pipefail
TASK_ROOT="$PWD"
python3 - <<'PY'
from pathlib import Path
import hashlib
for n,h in [('rustc.tar.xz','acdcdfe09ae1f103aa9a2b7f88903a9588bc2e99288af10e6fbf5514e2e49f25'),('rust-std.tar.xz','e25668477083d6a9ddb87b9beb9c00742225f38233ccb4bfba3afa7a07427f52')]:assert hashlib.sha256(Path(n).read_bytes()).hexdigest()==h
PY
mkdir toolchain
tar -xJf rustc.tar.xz --strip-components=2 -C toolchain rustc-1.99.1-aarch64-unknown-linux-gnu/rustc
tar -xJf rust-std.tar.xz --strip-components=2 -C toolchain rust-std-1.99.1-aarch64-unknown-linux-gnu/rust-std-aarch64-unknown-linux-gnu
python3 code/build.py --source source --out build --rustc "$TASK_ROOT/toolchain/bin/rustc"
/home/pi/adsb-neural-rescue/.venv/bin/python code/benchmark.py --root "$TASK_ROOT" --trials 5

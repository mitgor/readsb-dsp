#!/bin/bash
set -euo pipefail
TASK_ROOT="$PWD"
# Reuse the already checksum-verified temporary compiler. No system install.
"$TASK_ROOT/toolchain/bin/rustc" --version --verbose
python3 code-v2/build.py --source source --out build-v2 --selected-preset --rustc "$TASK_ROOT/toolchain/bin/rustc"
/home/pi/adsb-neural-rescue/.venv/bin/python code-v2/benchmark.py --root "$TASK_ROOT" --build "$TASK_ROOT/build-v2" --output "$TASK_ROOT/pi-v2.json" --trials 5

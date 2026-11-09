#!/bin/bash
set -euo pipefail
TASK_ROOT="$PWD"
mkdir build-v3
cp build-v2/stream-c build-v3/stream-c
cp build-v2/stream-profile build-v3/stream-profile
mkdir -p tmp
export TMPDIR="$TASK_ROOT/tmp"
# The unchanged C++ control was built with the same selected 2.4 MHz / 8 MHz preset.
python3 code-v3/build.py --source source --out build-v3 --modes rust --selected-preset --rustc "$TASK_ROOT/toolchain/bin/rustc"
/home/pi/adsb-neural-rescue/.venv/bin/python code-v3/benchmark.py --root "$TASK_ROOT" --build "$TASK_ROOT/build-v3" --output "$TASK_ROOT/pi-final.json" --trials 5

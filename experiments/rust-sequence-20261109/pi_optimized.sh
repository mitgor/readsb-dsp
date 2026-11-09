#!/bin/bash
set -euo pipefail
TASK_ROOT="$PWD"
cp -a reference optimized
cp build/c.so optimized/src/rescue/_pipeline_v3.so
PYTHONPATH="$TASK_ROOT/optimized/src" /home/pi/adsb-neural-rescue/.venv/bin/python experiments/rust-sequence-20261109/full_replay.py --stage "$TASK_ROOT" --output "$TASK_ROOT/full-c-optimized.private.json"

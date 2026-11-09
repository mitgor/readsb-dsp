#!/bin/bash
set -euo pipefail
cc -O2 code-complete/memory.c -o memory-launcher
/home/pi/adsb-neural-rescue/.venv/bin/python code-complete/benchmark.py --root "$PWD" --build "$PWD/build-v3" --output "$PWD/pi-final.json" --trials 5
/home/pi/adsb-neural-rescue/.venv/bin/python code-complete/timing.py --root "$PWD"

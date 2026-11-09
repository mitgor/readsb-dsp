#!/bin/bash
set -euo pipefail
python3 code-paired/patch_paired.py "$PWD"
PYTHONPATH="$PWD/paired/src" /home/pi/adsb-neural-rescue/.venv/bin/python code-paired/paired.py --root "$PWD"

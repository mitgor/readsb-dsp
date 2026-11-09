#!/bin/bash
set -euo pipefail
PYTHONPATH="$PWD/paired/src" /home/pi/adsb-neural-rescue/.venv/bin/python code-paired-v2/paired.py --root "$PWD"

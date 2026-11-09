#!/bin/bash
set -euo pipefail
/home/pi/adsb-neural-rescue/.venv/bin/python code-timing/timing.py --root "$PWD"

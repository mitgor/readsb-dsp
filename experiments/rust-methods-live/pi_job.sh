#!/bin/bash
set -euo pipefail
TASK_ROOT="$PWD"
mkdir toolchain
tar -xJf rustc.tar.xz --strip-components=2 -C toolchain rustc-1.99.1-aarch64-unknown-linux-gnu/rustc
tar -xJf rust-std.tar.xz --strip-components=2 -C toolchain rust-std-1.99.1-aarch64-unknown-linux-gnu/rust-std-aarch64-unknown-linux-gnu
P=/home/pi/adsb-neural-rescue/.venv/bin/python
"$P" tools/build_rust_methods.py --rustc "$TASK_ROOT/toolchain/bin/rustc" --output candidate > build.log 2>&1
cp candidate/_acquisition_rust.so candidate/_science_em_rust.so candidate/_science.so src/rescue/
mkdir -p parity
cp /home/pi/adsb-neural-rescue/src/rescue/_pipeline_extended_neon.so parity/c.so
cp candidate/_acquisition_rust.so parity/rust.so
cp blocks.bin iq-blocks.bin parity/
"$P" experiments/rust-acquisition/controls.py --work parity --decoder-root "$TASK_ROOT" --output controls.json
"$P" experiments/rust-acquisition/packet_replay.py --work parity --decoder-root "$TASK_ROOT" --output packets.json
"$P" experiments/rust-methods-live/validate.py "$TASK_ROOT" release.json

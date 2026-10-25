#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare the pinned readsb DSP source in a NEW checkout; never install it."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None, capture=False):
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def prepare(destination, source=None, build=False, rtlsdr=False, jobs=2):
    manifest = json.loads((ROOT/'manifest.json').read_text())
    # Verify the complete distribution before creating any checkout.
    for patch in manifest['patches']:
        path = ROOT/patch['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != patch['sha256']:
            raise ValueError(f'Patch checksum mismatch: {patch["file"]}')
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise ValueError(f'Destination already exists; choose a new directory: {destination}')
    if jobs < 1 or jobs > 64:
        raise ValueError('jobs must be between 1 and 64')
    destination.parent.mkdir(parents=True, exist_ok=True)
    run('git', 'clone', '--no-hardlinks', '--no-checkout', '--',
        str(source) if source else manifest['upstream'], str(destination))
    run('git', 'checkout', '--detach', manifest['base_commit'], cwd=destination)
    for patch in manifest['patches']:
        path = str(ROOT/patch['file'])
        run('git', 'apply', '--check', '--index', path, cwd=destination)
        run('git', 'apply', '--index', path, cwd=destination)
    actual = run('git', 'write-tree', cwd=destination, capture=True).strip()
    if actual != manifest['result_tree']:
        raise ValueError(f'Patched tree mismatch: {actual}')
    if build:
        run('make', f'-j{jobs}', f'RTLSDR={"yes" if rtlsdr else "no"}', cwd=destination)
    print(f'Prepared readsb {manifest["base_version"]} + DSP package {manifest["version"]}: {destination}')
    print('No binaries installed; no receiver, service or feeder settings changed.')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--source', help='Optional local readsb clone containing the pinned base (read-only source)')
    parser.add_argument('--build', action='store_true', help='Compile in the new checkout; never install')
    parser.add_argument('--rtlsdr', action='store_true', help='Enable RTL-SDR support when building')
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    try:
        prepare(args.destination, args.source, args.build, args.rtlsdr, args.jobs)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Preparation failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

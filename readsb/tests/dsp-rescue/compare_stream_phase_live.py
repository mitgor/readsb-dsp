#!/usr/bin/env python3
"""Replay a bounded live RSC1 capture through upstream Stream1090 and native C.

The input is the research-only framed I/Q copy from rescue.mac_bridge, not an
SDR or feeder socket. Both decoders see identical 1-second RF windows with
600 samples of context on each side. No packets are forwarded anywhere.
"""
import argparse
from collections import defaultdict
import ctypes
import hashlib
import json
from pathlib import Path
import resource
import statistics
import struct
import subprocess
import time
import zlib

RATE = 2_400_000
HALO = 600
TOTAL = RATE + 2 * HALO
WIRE = struct.Struct('!II')
TAP = struct.Struct('<4sIIIQQQ')
CALLBACK = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_int64, ctypes.c_void_p)


def zero_crc(message):
    crc = 0
    for value in message:
        for bit in range(7, -1, -1):
            top = (crc >> 23) ^ ((value >> bit) & 1)
            crc = (crc << 1) & 0xffffff
            if top:
                crc ^= 0xfff409
    return crc == 0


def unique(rows):
    by_payload = defaultdict(list)
    for tick, payload in sorted(rows):
        times = by_payload[payload]
        if not times or tick - times[-1] > 1440:
            times.append(tick)
    return [(tick, payload) for payload, times in by_payload.items() for tick in times]


def pair(native, old):
    native = unique(native)
    old = unique(old)
    used = set()
    both, native_only = [], []
    by_payload = defaultdict(list)
    for i, (tick, payload) in enumerate(old):
        by_payload[payload].append((i, tick))
    for tick, payload in native:
        options = [(abs(other-tick), i, other) for i, other in by_payload[payload]
                   if i not in used and abs(other-tick) <= 1440]
        if options:
            _, i, other = min(options)
            used.add(i)
            both.append((tick, payload, other-tick))
        else:
            native_only.append((tick, payload))
    old_only = [row for i, row in enumerate(old) if i not in used]
    return both, native_only, old_only


def read_packets(path):
    with path.open('rb') as stream:
        while header := stream.read(WIRE.size):
            if len(header) != WIRE.size:
                break  # bounded capture can stop between header bytes
            length, checksum = WIRE.unpack(header)
            if not TAP.size <= length <= 60040:
                raise ValueError('invalid wire length')
            packet = stream.read(length)
            if len(packet) != length:
                break  # only the final frame can be partial at end of capture
            if zlib.crc32(packet) != checksum:
                raise ValueError('corrupt RF frame')
            magic, epoch, rate, size, sample, ns, dropped = TAP.unpack_from(packet)
            if magic != b'RSC1' or rate != RATE or size != length-TAP.size or size % 2:
                raise ValueError('invalid RSC1 RF packet')
            yield epoch, sample, ns, dropped, packet[TAP.size:]


def run(old_binary, native_lib, raw, first, epoch, wall_start_ns):
    native = []
    def emit(pointer, bit_sample, unused):
        message = ctypes.string_at(pointer, 14)
        if message[0] >> 3 == 17 and zero_crc(message):
            native.append(((bit_sample-64)*3//2, message.hex()))
    callback = CALLBACK(emit)
    buf = ctypes.create_string_buffer(raw)
    before = time.process_time()
    native_lib.dspStreamPhase(ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8)),
                              len(raw)//2, first, first+HALO, callback, None,
                              2**63-1)
    native_cpu = time.process_time()-before
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    old_result = subprocess.run([str(old_binary), '-s', '2.4', '-u', '8'], input=raw,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=5, check=True)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    old_cpu = after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
    old = []
    for line in old_result.stdout.splitlines():
        if len(line) < 30 or line[:1] not in (b'<', b'@') or not line.endswith(b';'):
            continue
        try:
            tick = int(line[1:13], 16) + first*5 - 1630
            payload = line[15:-1] if line[:1] == b'<' else line[13:-1]
            message = bytes.fromhex(payload.decode())
        except (ValueError, UnicodeDecodeError):
            continue
        if len(message) == 14 and message[0] >> 3 == 17 and zero_crc(message):
            old.append((tick, message.hex()))
    start, end = (first+HALO)*5, (first+HALO+RATE)*5
    native = [(t, m) for t, m in native if start <= t < end]
    old = [(t, m) for t, m in old if start <= t < end]
    both, native_only, old_only = pair(native, old)
    return {'epoch': epoch, 'first_sample': first, 'wall_start_ns': wall_start_ns,
            'rf_sha256': hashlib.sha256(raw).hexdigest(),
            'both': len(both), 'native_only': len(native_only), 'old_only': len(old_only),
            'native_cpu_s': native_cpu, 'old_cpu_s': old_cpu,
            'paired_offset_ticks': statistics.median(x[2] for x in both) if both else None,
            'both_rows': both, 'native_only_rows': native_only, 'old_only_rows': old_only}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture', type=Path, required=True)
    ap.add_argument('--old-binary', type=Path, required=True)
    ap.add_argument('--native-lib', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--limit-seconds', type=int, default=0)
    args = ap.parse_args()
    lib = ctypes.CDLL(str(args.native_lib.resolve()))
    lib.dspStreamPhase.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint,
                                   ctypes.c_int64, ctypes.c_int64, CALLBACK,
                                   ctypes.c_void_p, ctypes.c_int64]
    lib.dspStreamPhase.restype = None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    epoch = expected = first = anchor_sample = anchor_ns = None
    samples = bytearray()
    gaps = frames = processed = 0
    totals = defaultdict(float)
    started = time.monotonic()
    with args.output.open('w') as report:
        for packet_epoch, sample, ns, dropped, raw in read_packets(args.capture):
            frames += 1
            if packet_epoch != epoch or sample != expected:
                gaps += epoch is not None
                epoch = packet_epoch
                skip = -sample % 3
                first = sample+skip
                anchor_sample, anchor_ns = sample, ns
                samples.clear()
                samples.extend(raw[2*skip:])
            else:
                samples.extend(raw)
            expected = sample+len(raw)//2
            while len(samples) >= 2*TOTAL:
                window = bytes(samples[:2*TOTAL])
                wall_start_ns = anchor_ns + (first-anchor_sample)*1_000_000_000//RATE
                result = run(args.old_binary, lib, window, first, epoch, wall_start_ns)
                report.write(json.dumps(result, separators=(',', ':'))+'\n')
                for key in ('both', 'native_only', 'old_only', 'native_cpu_s', 'old_cpu_s'):
                    totals[key] += result[key]
                processed += 1
                if processed % 30 == 0:
                    print(json.dumps({'seconds': processed, 'frames': frames,
                                      'gaps': gaps, 'totals': totals}), flush=True)
                    report.flush()
                del samples[:2*RATE]
                first += RATE
                if args.limit_seconds and processed >= args.limit_seconds:
                    break
            if args.limit_seconds and processed >= args.limit_seconds:
                break
    summary = {'processed_rf_seconds': processed, 'input_frames': frames,
               'discontinuities': gaps, 'totals': dict(totals),
               'analysis_wall_s': time.monotonic()-started,
               'capture': str(args.capture), 'old_binary': str(args.old_binary),
               'native_lib': str(args.native_lib)}
    args.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()

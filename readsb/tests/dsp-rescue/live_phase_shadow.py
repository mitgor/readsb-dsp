"""Bounded live native phase observer using the existing nonblocking IQ mirror.

Install this module alongside rescue.stream1090_shadow. It reads only the
research IQ datagram socket, stock Beast, and DSP comparison datagrams; it has
no feeder output socket. Repaired messages are observations, never forwarded.
"""
import argparse
import bisect
import ctypes
import json
import queue
import signal
import socket
import threading
import time
from collections import deque
from pathlib import Path

from .stream1090_shadow import (Shadow, compare, valid_df17)
from .wire import BeastParser

CALLBACK = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_int64,
                            ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p)
BITMAP_BYTES = 1 << 21
CORE_START = 600
CORE_SAMPLES = 2_400_000
TICKS_PER_SECOND = 12_000_000


class NativePhaseShadow(Shadow):
    def __init__(self, args):
        super().__init__(args)
        self.library = ctypes.CDLL(str(Path(args.binary).resolve()))
        self.library.dspStreamPhaseRepair.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint,
            ctypes.c_int64, ctypes.c_int64, CALLBACK, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_int64]
        self.library.dspStreamPhaseRepair.restype = None
        self.expires = time.monotonic() + args.duration
        self.extra_kinds = {}
        self.unified = deque()
        self.unified_lock = threading.Lock()
        self.unified_latest_tick = 0
        self.event_log = Path(args.status).with_suffix('.events.jsonl')

    def read_stock(self):
        # Retain the full production identity window. The parent observer's
        # eight-second history is sufficient for overlap but not this guard.
        while not self.stop.is_set():
            try:
                with socket.create_connection(('127.0.0.1', 30005), timeout=2) as sock:
                    sock.settimeout(1)
                    parser = BeastParser()
                    self.count['stock_connections'] += 1
                    while not self.stop.is_set():
                        try:
                            chunk = sock.recv(65536)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        now = time.time()
                        rows = [(r['ticks_12mhz']-2398, r['message_hex'])
                                for r in parser.feed(chunk) if valid_df17(r['message_hex'])]
                        with self.stock_lock:
                            self.stock.extend((now, tick, message) for tick, message in rows)
                            while self.stock and now-self.stock[0][0] > 40:
                                self.stock.popleft()
            except (OSError, ValueError):
                self.count['stock_disconnects'] += 1
            self.stop.wait(1)

    def read_unified(self):
        while not self.stop.is_set():
            try:
                with socket.create_connection(('127.0.0.1', 31005), timeout=2) as sock:
                    sock.settimeout(1)
                    parser = BeastParser()
                    self.count['unified_connections'] += 1
                    while not self.stop.is_set():
                        try:
                            chunk = sock.recv(65536)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        now = time.time()
                        rows = [(r['ticks_12mhz']-2398, r['message_hex'])
                                for r in parser.feed(chunk) if valid_df17(r['message_hex'])]
                        with self.unified_lock:
                            self.unified.extend((now, tick, message) for tick, message in rows)
                            if rows:
                                self.unified_latest_tick = max(self.unified_latest_tick,
                                                               max(t for t, _ in rows))
                            cutoff = now-40
                            while self.unified and self.unified[0][0] < cutoff:
                                self.unified.popleft()
            except (OSError, ValueError):
                self.count['unified_disconnects'] += 1
            self.stop.wait(1)

    def worker(self):
        bitmap = (ctypes.c_uint8 * BITMAP_BYTES)()
        while not self.stop.is_set():
            try:
                epoch, first, wall, raw = self.jobs.get(timeout=.5)
            except queue.Empty:
                continue
            if time.time() - wall > 5:
                self.count['stale_rf_seconds'] += 1
                continue
            begin = time.process_time()
            try:
                start = (first + CORE_START) * 5
                end = start + TICKS_PER_SECOND
                with self.stock_lock:
                    frames = [(t, m) for _, t, m in self.stock]
                ctypes.memset(bitmap, 0, BITMAP_BYTES)
                for tick, message in frames:
                    if start - 30*TICKS_PER_SECOND <= tick < start:
                        addr = int(message[2:8], 16)
                        bitmap[addr >> 3] |= 1 << (addr & 7)
                raw_buffer = ctypes.create_string_buffer(raw)
                seen = []

                def emit(pointer, bit_sample, corrected, kind, unused):
                    message = ctypes.string_at(pointer, 14).hex()
                    tick = (bit_sample - 64) * 3 // 2
                    if start <= tick < end and valid_df17(message):
                        seen.append((tick, message, int(corrected), int(kind)))

                callback = CALLBACK(emit)
                self.library.dspStreamPhaseRepair(
                    ctypes.cast(raw_buffer, ctypes.POINTER(ctypes.c_uint8)),
                    len(raw)//2, first, first+CORE_START, callback, None,
                    bitmap, 2**63-1)
                candidates = [(tick, message) for tick, message, _, _ in seen]
                kind_by_row = {}
                for tick, message, _, kind in seen:
                    key = (tick, message)
                    kind_by_row[key] = min(kind, kind_by_row.get(key, kind))
                alignment, extras = compare(candidates, frames)
                self.last_alignment = alignment
                self.count['processed_rf_seconds'] += 1
                self.count['native_df17'] += len(seen)
                self.count['decoder_cpu_us'] += round((time.process_time()-begin)*1e6)
                self.count['clean_candidates'] += sum(kind == 0 for *_, kind in seen)
                self.count['table_candidates'] += sum(kind == 1 for *_, kind in seen)
                self.count['erasure_candidates'] += sum(kind == 2 for *_, kind in seen)
                if alignment['aligned']:
                    self.count['aligned_rf_seconds'] += 1
                    self.count['not_seen_stock'] += len(extras)
                    offset = alignment['offset_ticks']
                    for tick, message in extras:
                        kind = kind_by_row.get((tick-offset, message), -1)
                        bin_name = self.range_bin(message)
                        self.count['extra_'+bin_name] += 1
                        self.count[f'extra_kind_{kind}'] += 1
                        self.recent.append({'unix': wall+(tick-first*5)/TICKS_PER_SECOND,
                                            'message_hex': message, 'kind': kind,
                                            'distance_bin_nm': bin_name,
                                            'research_only': True})
                    with self.compare_lock:
                        for tick, message in extras:
                            self.extra_kinds[(epoch, tick, message)] = kind_by_row.get((tick-offset, message), -1)
                        self.stream_windows.append({'epoch': epoch, 'start': start,
                                                    'end': end, 'wall': wall,
                                                    'extras': [(t,m) for t,m in extras if start<=t<end],
                                                    'at': time.monotonic(), 'matched': False})
                else:
                    self.count['unaligned_rf_seconds'] += 1
                self.last_complete = time.time()
            except Exception as error:
                self.last_error = repr(error)
                self.count['decoder_errors'] += 1

    def finalize_comparisons(self):
        now = time.monotonic()
        ready = []
        with self.compare_lock:
            while self.stream_windows and now-self.stream_windows[0]['at'] > 5:
                window = self.stream_windows.popleft()
                ready.append(window)
        with self.unified_lock:
            unified = [(tick, message) for _, tick, message in self.unified]
            latest = self.unified_latest_tick
        by_payload = {}
        for tick, message in unified:
            by_payload.setdefault(message, []).append(tick)
        for times in by_payload.values():
            times.sort()
        for window in ready:
            epoch = window['epoch']
            if latest < window['end'] + TICKS_PER_SECOND:
                self.count['unified_incomplete_rf_seconds'] += 1
                continue
            self.count['matched_rf_seconds'] += 1
            for tick, message in window['extras']:
                kind = self.extra_kinds.get((epoch, tick, message), -1)
                times = by_payload.get(message, ())
                i = bisect.bisect_left(times, tick-1440)
                if i < len(times) and times[i] <= tick+1440:
                    self.count['overlap_unified'] += 1
                    continue
                self.count['unique_over_unified'] += 1
                self.count[f'unique_kind_{kind}'] += 1
                bin_name = self.range_bin(message)
                self.count['unique_'+bin_name] += 1
                unix = window['wall'] + (tick-(window['start']-CORE_START*5))/TICKS_PER_SECOND
                row = {'epoch': epoch, 'ticks': tick, 'unix': unix, 'message_hex': message,
                       'kind': kind, 'distance_bin_nm': bin_name, 'research_only': True}
                self.recent_unique.append(row)
                if not self.event_log.exists() or self.event_log.stat().st_size < 16_000_000:
                    with self.event_log.open('a') as output:
                        output.write(json.dumps(row, separators=(',', ':'))+'\n')
                else:
                    self.count['event_log_cap_skips'] += 1
            for tick, message in window['extras']:
                self.extra_kinds.pop((epoch, tick, message), None)

    def write_status(self):
        status = {'updated_unix': time.time(), 'started_unix': self.started,
                  'mode': 'native_phase_research_shadow', 'forwarding_enabled': False,
                  'library': self.args.binary, 'source_commit': self.args.commit,
                  'counts': dict(self.count), 'pending_rf_seconds': self.jobs.qsize(),
                  'pending_comparison_seconds': len(self.stream_windows),
                  'last_alignment': self.last_alignment,
                  'last_complete_unix': self.last_complete,
                  'last_error': self.last_error,
                  'recent_absent_from_stock': list(self.recent),
                  'recent_incremental': list(self.recent_unique),
                  'interpretation': ('Kinds 0/1/2 are clean/table/erasure. '
                                     'Stock prior identity comes from Beast, which does not expose '
                                     'readsb corrected-bit flags; counts are permissive shadow estimates, '
                                     'not independent truth or feeder-eligible. Unique means absent from '
                                     'observed unified Beast within 120 us, for complete compared RF seconds.')}
        target = Path(self.args.status)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(status, separators=(',', ':')))
        temporary.replace(target)

    def run(self):
        timer = threading.Timer(max(0, self.expires-time.monotonic()), self.stop.set)
        timer.daemon = True
        timer.start()
        try:
            threads = [threading.Thread(target=f, daemon=True)
                       for f in (self.read_stock, self.read_unified, self.receiver, self.worker)]
            for thread in threads:
                thread.start()
            try:
                while not self.stop.wait(2):
                    self.finalize_comparisons()
                    self.write_status()
            finally:
                self.stop.set()
                self.sock.close()
                for thread in threads:
                    thread.join(timeout=4)
                self.finalize_comparisons()
                self.write_status()
                self.path.unlink(missing_ok=True)
        finally:
            timer.cancel()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True, help='native phase shared library')
    parser.add_argument('--commit', required=True)
    parser.add_argument('--socket', default='/run/adsb-rescue/stream1090-iq.sock')
    parser.add_argument('--status', default='/run/adsb-rescue/native-phase-status.json')
    parser.add_argument('--lat', type=float, required=True)
    parser.add_argument('--lon', type=float, required=True)
    parser.add_argument('--duration', type=int, default=1800)
    args = parser.parse_args()
    if not 60 <= args.duration <= 3600:
        parser.error('duration must be 60–3600 seconds')
    shadow = NativePhaseShadow(args)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: shadow.stop.set())
    shadow.run()


if __name__ == '__main__':
    main()

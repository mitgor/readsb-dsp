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
import statistics
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from .stream1090_shadow import (Shadow, compare, parse_avr, valid_df17)
from .wire import BeastParser

CALLBACK = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_int64,
                            ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p)
BITMAP_BYTES = 1 << 21
CORE_START = 600
CORE_SAMPLES = 2_400_000
TICKS_PER_SECOND = 12_000_000
MATCH_TICKS = 1440


def unique_events(rows):
    by_message = {}
    result = []
    for tick, message in sorted(rows):
        times = by_message.setdefault(message, [])
        if times and tick-times[-1] <= MATCH_TICKS:
            continue
        times.append(tick)
        result.append((tick, message))
    return result


def pair_events(reference, candidates):
    """One-to-one exact-payload matching within 120 microseconds."""
    reference = unique_events(reference)
    candidates = unique_events(candidates)
    indexed = {}
    for index, (tick, message) in enumerate(candidates):
        indexed.setdefault(message, []).append((tick, index))
    used = set()
    matched = []
    missing = []
    for tick, message in reference:
        options = [(abs(other-tick), index) for other, index in indexed.get(message, ())
                   if index not in used and abs(other-tick) <= MATCH_TICKS]
        if options:
            _, index = min(options)
            used.add(index)
            matched.append((tick, message))
        else:
            missing.append((tick, message))
    return matched, missing, [row for index, row in enumerate(candidates) if index not in used]


def calibrate_old(old, native_clean):
    """Estimate the residual after the pinned old AVR clock's 1,630-tick offset."""
    clean_by_message = {}
    for tick, message in unique_events(native_clean):
        clean_by_message.setdefault(message, []).append(tick)
    deltas = []
    for tick, message in unique_events(old):
        nearby = [other-tick for other in clean_by_message.get(message, ())
                  if abs(other-tick) <= 5000]
        if nearby:
            deltas.append(min(nearby, key=abs))
    if len(deltas) < 10:
        return None, {'aligned':False,'shared':len(deltas),'reason':'too_few_shared_clean'}
    offset = round(statistics.median(deltas))
    mad = statistics.median(abs(delta-offset) for delta in deltas)
    if mad > 360:
        return None, {'aligned':False,'shared':len(deltas),'mad_ticks':mad,
                      'reason':'unstable_clock'}
    return offset, {'aligned':True,'shared':len(deltas),'offset_ticks':offset,
                    'mad_ticks':mad}


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
        self.comparison_log = Path(args.status).with_suffix('.direct.jsonl')
        self.last_direct_alignment = {}

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
                if self.args.old_binary:
                    self.compare_old(epoch, raw, first, start, end, frames, seen)
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

    def compare_old(self, epoch, raw, first, start, end, stock_frames, native_seen):
        """Compare the pinned old executable and native C on this exact IQ."""
        try:
            result = subprocess.run([self.args.old_binary, '-s', '2.4', '-u', '8'],
                                    input=raw, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=2, check=True)
            old = [(tick-1630, message) for tick, message in parse_avr(result.stdout, first)]
            clean = [(tick, message) for tick, message, _, kind in native_seen if kind == 0]
            offset, alignment = calibrate_old(old, clean)
            self.last_direct_alignment = alignment
            if offset is None:
                self.count['direct_unaligned_rf_seconds'] += 1
                return
            old = [(tick+offset, message) for tick, message in old
                   if start <= tick+offset < end]
            clean = [(tick, message) for tick, message in clean if start <= tick < end]
            repaired = [(tick, message) for tick, message, _, kind in native_seen
                        if kind > 0 and start <= tick < end]
            native = [(tick, message) for tick, message, _, _ in native_seen
                      if start <= tick < end]
            _, old_only_clean, _ = pair_events(old, clean)
            recovered, unrecovered, _ = pair_events(old_only_clean, repaired)
            full_matched, full_missed, native_only = pair_events(old, native)
            stock_index = {}
            for tick, message in stock_frames:
                stock_index.setdefault(message, []).append(tick)
            def absent_stock(rows):
                return sum(not any(abs(tick-other) <= MATCH_TICKS
                                   for other in stock_index.get(message, ()))
                           for tick, message in rows)
            counts = {
                'old_total': len(unique_events(old)),
                'native_clean_total': len(unique_events(clean)),
                'native_all_total': len(unique_events(native)),
                'old_only_clean': len(old_only_clean),
                'old_only_clean_recovered_by_repair': len(recovered),
                'old_only_clean_remaining': len(unrecovered),
                'old_full_matched': len(full_matched),
                'old_full_missed': len(full_missed),
                'native_only': len(native_only),
                'old_only_clean_beyond_stock': absent_stock(old_only_clean),
                'old_only_clean_recovered_beyond_stock': absent_stock(recovered),
                'native_only_beyond_stock': absent_stock(native_only),
            }
            self.count['direct_paired_rf_seconds'] += 1
            for key, value in counts.items():
                self.count['direct_'+key] += value
            row = {'epoch':epoch, 'first_sample':first, 'wall':time.time(),
                   'alignment':alignment, 'counts':counts}
            if not self.comparison_log.exists() or self.comparison_log.stat().st_size < 8_000_000:
                with self.comparison_log.open('a') as output:
                    output.write(json.dumps(row, separators=(',', ':'))+'\n')
            else:
                self.count['direct_log_cap_skips'] += 1
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            self.count['direct_decoder_errors'] += 1
            self.last_error = 'old_decoder: '+repr(error)

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
                  'last_direct_alignment': self.last_direct_alignment,
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
    parser.add_argument('--old-binary', help='pinned Stream1090 executable for direct IQ pairing')
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

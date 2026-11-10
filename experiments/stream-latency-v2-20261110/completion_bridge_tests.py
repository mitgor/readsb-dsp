"""Bounded, causal event/retry controls. No receiver connection or output socket."""
import argparse
import json
from pathlib import Path

from completion_bridge import Bridge
from rescue.shadow import valid_df17
from rescue.stock_history import StockHistory


def payload(i, icao=0xabcdef):
    value = (0x8d << 104) | (icao << 80) | (i << 24)
    remainder = value
    for bit in range(111, 23, -1):
        if remainder & (1 << bit):
            remainder ^= 0x1fff409 << (bit-24)
    result = f'{value | remainder:028x}'
    assert valid_df17(result)
    return result


def run(library=None):
    names = []
    for native in ([False, True] if library else [False]):
        prefix = 'rust_' if native else 'python_'
        engines = []
        def create(emit, **options):
            admission = None
            if native:
                from native_admission import NativeAdmission
                admission = NativeAdmission(library, epoch=7)
                engines.append(admission)
            return Bridge(7, emit, admission=admission, **options)
        first = 20000000
        start = (first+600)*5
        end = start+12000000
        target = payload(900)
        tick = start+300000
        anchors = [dict(source='energy', ticks=start+i*10000,
                        message_hex=payload(i+1)) for i in range(20)]
        history = StockHistory()
        for r in anchors:
            history.append(r)
        tail = dict(ticks=end+2000, message_hex=payload(901, 0x123456))
        history.append(tail)
        frames = history.snapshot()
        rows = [(r['ticks']+1631, r['message_hex']) for r in anchors]+[(tick+1631, target)]
        emitted = []
        bridge = create(lambda *args: emitted.append(args))
        bridge.begin(0, dict(first=first, epoch=7))
        bridge.offer(0, 'native', 7, rows, start+720000+1440, False)
        bridge.offer(0, 'energy', 7, anchors[:9], start+480000+1440, False)
        # Arrived native and energy do not grant stock-only identity or a clock.
        bridge.drain([], end+2000, .04)
        assert not emitted
        names.append(prefix+'unarrived_stock_cannot_authorize')
        for row in frames:
            bridge.on_stock(row)
        bridge.drain(frames, end+2000, .05)
        assert not emitted
        assert bridge.windows[0]['pending']
        names.append(prefix+'incomplete_energy_waits_instead_of_skipping')
        count = bridge.count.copy()
        for _ in range(100):
            bridge.drain(frames, end+2000, .051)
        assert bridge.count == count
        names.append(prefix+'idle_drains_do_no_work')
        bridge.offer(0, 'energy', 7, anchors[9:], start+720000+1440, False)
        bridge.drain(frames, end+2000, .06)
        assert any(r[0]['message_hex'] == target and r[3] == 'early' for r in emitted)
        assert bridge.count['finalized_windows'] == 0
        names.append(prefix+'cold_slice_retried_on_arrived_evidence')
        before = len(emitted)
        bridge.offer(0, 'native', 8, [(tick+1631, target)], end+1440, True)
        bridge.drain(frames, end+2000, .07)
        assert len(emitted) == before and bridge.count['wrong_epoch'] == 1
        names.append(prefix+'wrong_epoch_cannot_publish')
        try:
            bridge.offer(0, 'native', 7, [(tick, '8d'+'00'*13)], end+1440, False)
            raise AssertionError('Invalid CRC accepted')
        except ValueError:
            names.append(prefix+'invalid_CRC_rejected')
        try:
            bridge.offer(0, 'energy', 7, [], 1, False)
            raise AssertionError('Backwards watermark accepted')
        except ValueError:
            names.append(prefix+'backwards_watermark_rejected')
        bridge.offer(0, 'native', 7, [], end+1440, True)
        bridge.offer(0, 'energy', 7, [], end+1440, True)
        bridge.drain(frames, end+2000, 1.01)
        assert bridge.pending() == 0
        assert any(r[0]['message_hex'] == target and r[3] == 'final' for r in emitted)
        names.append(prefix+'unchanged_final_fallback_no_redecode')
        bridge.offer(0, 'energy', 7, [anchors[0]], end+1440, True)
        assert bridge.count['late_result'] == 1
        names.append(prefix+'closed_window_rejects_late_completion')
        bounded = create(lambda *args: None, max_windows=1)
        bounded.begin(0, dict(first=first))
        try:
            bounded.begin(1, dict(first=first+2400000))
            raise AssertionError('Unbounded active windows')
        except BufferError:
            names.append(prefix+'active_windows_bounded_without_eviction')
        bounded = create(lambda *args: None, max_rows_per_window=1)
        bounded.begin(0, dict(first=first))
        try:
            bounded.offer(0, 'native', 7, rows, end+1440, False)
            raise AssertionError('Unbounded candidate count')
        except BufferError:
            names.append(prefix+'producer_rows_bounded')
        for engine in engines:
            engine.close()
    return dict(all_passed=True, checks=names, production_actions=[])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        assert not args.output.exists()
    result = run(args.library)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))

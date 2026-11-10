"""Synthetic retry-state controls; no RF labels, sockets or receiver access."""
import json
import unittest
from cold_start import ColdStartRetry


class RetryTests(unittest.TestCase):
    def test_later_arrived_evidence_retries_older_pending_slice(self):
        r = ColdStartRetry()
        p = {0: (100, 200)}
        self.assertEqual(r.select(1, p, 200, (1, 1, 1), .02), [0])
        # Failed admission leaves it pending; later completed energy/stock is
        # allowed to authorize a new *attempt*, never acceptance by this helper.
        self.assertEqual(r.select(1, p, 400, (2, 2, 2), .04), [0])

    def test_wall_time_does_not_retry_unchanged_evidence(self):
        r = ColdStartRetry(); p = {0: (100, 200)}
        self.assertEqual(r.select(1, p, 200, (1, 1, 1), .02), [0])
        self.assertEqual(r.select(1, p, 200, (1, 1, 1), 1000), [])

    def test_future_RF_coverage_never_selected(self):
        r = ColdStartRetry(); p = {0: (100, 200)}
        self.assertEqual(r.select(1, p, 199, (1, 1, 1), 1), [])
        self.assertEqual(r.select(1, p, 200, (1, 1, 2), 2), [0])

    def test_sorted_once_per_revision(self):
        r = ColdStartRetry(); p = {2: (300, 400), 0: (100, 200), 1: (200, 300)}
        self.assertEqual(r.select(1, p, 400, (1, 1, 1), 1), [0, 1, 2])
        self.assertEqual(r.select(1, p, 400, (1, 1, 1), 2), [])

    def test_resolved_slice_cannot_be_selected_again(self):
        r = ColdStartRetry(); p = {0: (100, 200)}
        r.select(1, p, 200, (1, 1, 1), 1); r.resolved(1, 0)
        self.assertEqual(r.pending_count, 0)
        self.assertEqual(r.select(1, p, 300, (2, 2, 2), 2), [])

    def test_window_cap_preserves_active_work(self):
        r = ColdStartRetry(max_windows=1); p = {0: (100, 200)}
        r.select('a', p, 200, (1,), 1)
        with self.assertRaises(BufferError): r.select('b', p, 200, (1,), 1)
        self.assertEqual(list(r.windows), ['a'])

    def test_total_pending_cap_is_atomic(self):
        r = ColdStartRetry(max_pending=1); p = {0: (100, 200)}
        r.select('a', p, 200, (1,), 1)
        with self.assertRaises(BufferError): r.select('b', p, 200, (1,), 1)
        self.assertEqual(r.pending_count, 1); self.assertNotIn('b', r.windows)

    def test_slice_cap(self):
        r = ColdStartRetry(max_slices=1)
        with self.assertRaises(BufferError): r.select('a', {0:(1,2), 1:(2,3)}, 3, (1,), 1)
        self.assertEqual(r.pending_count, 0)

    def test_close_rejects_stale_work_and_releases_capacity(self):
        r = ColdStartRetry(max_windows=1); p = {0: (100, 200)}
        r.select('a', p, 200, (1,), 1); r.close('a')
        self.assertEqual(r.pending_count, 0)
        with self.assertRaises(ValueError): r.select('a', p, 200, (2,), 2)
        self.assertEqual(r.select('b', p, 200, (1,), 1), [0])

    def test_reset_clears_epoch_owned_state(self):
        r = ColdStartRetry(); p = {0:(100,200)}
        r.select('a', p, 200, (1,), 1); r.close('a'); r.reset()
        self.assertEqual(r.select('a', p, 200, (1,), 1), [0])

    def test_backwards_revision_coverage_or_time_rejected(self):
        for revision, end, now in [((0,1,1),200,2), ((1,1,2),199,2), ((1,1,2),200,.5)]:
            r=ColdStartRetry();p={0:(100,200)};r.select(1,p,200,(1,1,1),1)
            with self.assertRaises(ValueError):r.select(1,p,end,revision,now)

    def test_pending_RF_identity_immutable(self):
        r=ColdStartRetry();r.select(1,{0:(100,200)},200,(1,),1)
        with self.assertRaises(ValueError):r.select(1,{0:(101,200)},200,(2,),2)

    def test_completion_bridge_uses_drop_in_policy(self):
        try:
            import completion_bridge_tests as controls
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.startswith('rescue'):
                self.skipTest('Copied production runtime not on PYTHONPATH')
            raise
        original = controls.Bridge
        def bridge(*args, **kwargs):
            kwargs.setdefault('retry', ColdStartRetry())
            return original(*args, **kwargs)
        controls.Bridge = bridge
        try:
            result = controls.run()
        finally:
            controls.Bridge = original
        self.assertTrue(result['all_passed'])
        self.assertIn('python_cold_slice_retried_on_arrived_evidence', result['checks'])

    def test_bad_input_and_bounds(self):
        for kwargs in [dict(max_windows=0),dict(max_slices=51),dict(max_pending=True)]:
            with self.assertRaises(ValueError):ColdStartRetry(**kwargs)
        r=ColdStartRetry()
        for revision in [(),(True,),(-1,),[1]]:
            with self.assertRaises(ValueError):r.select(1,{0:(100,200)},200,revision,1)
        self.assertEqual(len(r.windows),0)


if __name__ == '__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(RetryTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'tests':result.testsRun,'passed':result.wasSuccessful()}))
    raise SystemExit(not result.wasSuccessful())

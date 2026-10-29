import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock
from concurrent.futures import Future
from collections import Counter,deque
from rescue.workers import topology,plan,cpu_list,WorkerPool,block_ranges,merge_events
class WorkerTests(unittest.TestCase):
    def mock_pool(self,count):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        pool=object.__new__(WorkerPool);pool.selection={'workers':count};pool.pending=deque();pool.completed=Counter();pool.cpu_seconds=Counter();pool.affinities={};pool.jobs=0;pool.recent_overlap=deque(maxlen=120);pool.executor=Mock();pool.runtime=Path(tmp.name);pool.job_paths=set()
        return pool
    @staticmethod
    def event(sample,source='energy'):
        return dict(sample_4msps=sample,message_hex='abc',source=source)
    @staticmethod
    def detail(pid):
        return dict(worker_pid=pid,worker_cpus=[],worker_cpu_s=.1,chunk_started_s=0.,chunk_finished_s=.1,block_range=(0,1))
    def test_chunk_ranges_cover_original_blocks_once(self):
        self.assertEqual(block_ranges(4802400,2),[(0,10),(10,21)])
        self.assertEqual(block_ranges(2,2),[(0,1)])
        for n in (0,3):
            with self.assertRaises(ValueError):block_ranges(n,2)
    def test_cross_chunk_dedupe_replays_emission_order_and_keeps_quarantine(self):
        # A suppresses B, but C must survive. Independently deduping B/C loses C.
        a,b,c=[self.event(n) for n in (0,440,840)]
        broad=self.event(440,'broad_crc')
        self.assertEqual(merge_events([[a],[b,c,broad,broad]]),[a,broad,broad,c])
        # Serial stage priority, not time sorting, decides which source wins.
        self.assertEqual(merge_events([[self.event(10)],[self.event(0,'timing')]]),[self.event(10)])
    def fixture(self,root,cpu,capacity,siblings=None,midr=None):
        p=root/f'cpu{cpu}';(p/'topology').mkdir(parents=True)
        if capacity is not None:(p/'cpu_capacity').write_text(str(capacity))
        (p/'topology/thread_siblings_list').write_text(siblings or str(cpu))
        if midr:
            (p/'regs/identification').mkdir(parents=True);(p/'regs/identification/midr_el1').write_text(midr)
    def test_big_little_and_smt_are_not_counted_as_extra_primary_cores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for cpu in range(8):self.fixture(root,cpu,1024 if cpu<4 else 512,('0,1' if cpu<2 else '2,3') if cpu<4 else None)
            info=topology(root,range(8));self.assertEqual(info['performance_cpus'],[0,2]);self.assertEqual(info['physical_core_count'],6)
            selected=plan(info=info);self.assertEqual(selected['workers'],1);self.assertEqual(selected['worker_cpus'],[2])
    def test_pi_four_equal_cores_reserves_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for cpu in range(4):self.fixture(root,cpu,1024)
            selected=plan(info=topology(root,range(4)))
            self.assertEqual(selected['workers'],2);self.assertEqual(selected['worker_cpus'],[2,3]);self.assertEqual(selected['reserved_performance_cpus'],[0,1])
    def test_identical_arm_fallback_and_unknown_class_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for cpu in range(4):self.fixture(root,cpu,None,midr='0x410fd083')
            info=topology(root,range(4));self.assertTrue(info['classification_verified']);self.assertEqual(plan(info=info)['workers'],2)
            (root/'cpu3/regs/identification/midr_el1').write_text('0x410fd050')
            info=topology(root,range(4));self.assertFalse(info['classification_verified'])
            with self.assertRaises(ValueError):plan(info=info)
    def test_coherent_cores_must_be_available_and_separate(self):
        info=dict(logical_cpus=[0,1,2,3],performance_cpus=[0,1,2,3],classification_verified=True)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'workers.json'
            p.write_text(json.dumps({'cpus':'2-3','coherent_cpus':'0-1'}))
            self.assertEqual(plan(p,info)['coherent_cpus'],[0,1])
            for cpus in ('1-2','4','',False):
                p.write_text(json.dumps({'cpus':'2-3','coherent_cpus':cpus}))
                with self.assertRaises(ValueError):plan(p,info)
    def test_manual_count_bounded_and_cpu_override_visible(self):
        info=dict(logical_cpus=[0,1,2,3],performance_cpus=[0,1,2,3],classification_verified=True)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'workers.json'
            for cfg in ({'workers':3},{'workers':True},{'cpus':'8'},{'max_workers':0},{'typo':1}):
                p.write_text(json.dumps(cfg))
                with self.assertRaises(ValueError):plan(p,info)
            p.write_text(json.dumps({'cpus':'1,3','workers':2}));self.assertEqual(plan(p,info)['worker_cpus'],[1,3])
    def test_ordered_delivery_and_pending_bound(self):
        pool=self.mock_pool(2)
        f1=Future();f2=Future();pool.executor.submit.side_effect=[f1,f2]
        pool.submit((1,0,0,b'raw1',0));pool.submit((1,1,1,b'raw2',0))
        with self.assertRaises(RuntimeError):pool.submit((1,2,2,b'raw3',0))
        f2.set_result(([self.event(2)],self.detail(2)));self.assertFalse(pool.ready());self.assertIsNone(pool.pop())
        f1.set_result(([self.event(1)],self.detail(1)));self.assertEqual(pool.pop()[1],[self.event(1)]);self.assertEqual(pool.pop()[1],[self.event(2)]);self.assertEqual(pool.completed,{'1':1,'2':1})

    def test_worker_failure_is_not_silently_counted(self):
        pool=self.mock_pool(1)
        f=Future();pool.executor.submit.return_value=f;pool.submit((1,0,0,b'xx',0));f.set_exception(RuntimeError('failed decoding'))
        with self.assertRaises(RuntimeError):pool.pop()
        self.assertFalse(pool.completed)

    def test_spawned_workers_match_single_process_and_clean_tmpfs_jobs(self):
        import os
        import numpy as np
        from rescue.runtime import RescueDecoder
        from rescue.pipeline import settings
        from rescue.native import library
        try:library()
        except OSError:self.skipTest('Build optional native frontend first')
        # Short deterministic capture: actual IPC, native pipeline and clean shutdown.
        raw=np.random.default_rng(251026).integers(110,145,size=600000,dtype=np.uint8).tobytes()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'reference.uc8';path.write_bytes(raw)
            d=RescueDecoder('unused',frontend='native',neural=False,broad_crc=True,methods=('timing','soft','matched'))
            expected,_=d.decode(path)
            allowed=sorted(os.sched_getaffinity(0))[-2:] if hasattr(os,'sched_getaffinity') else []
            pool=WorkerPool('unused',settings(),root,dict(workers=2,worker_cpus=allowed))
            try:
                for i in range(2):pool.submit((1,i,0,raw,time.monotonic()))
                for i in range(2):
                    deadline=time.monotonic()+30
                    while not pool.ready() and time.monotonic()<deadline:time.sleep(.01)
                    self.assertTrue(pool.ready());item,events,work=pool.pop()
                    self.assertEqual(item[1],i);self.assertEqual(events,expected);self.assertNotEqual(work['worker_pid'],os.getpid())
                self.assertEqual(sum(pool.completed.values()),4)
            finally:pool.close()
            self.assertFalse(list(root.glob('job-*.uc8')))

class CoherentTuningConfigTests(unittest.TestCase):
    def test_optimized_extended_is_explicit_and_requires_v3(self):
        info=dict(logical_cpus=[0,1,2,3],performance_cpus=[0,1,2,3],classification_verified=True)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'workers.json'
            cfg=dict(workers=2,max_workers=2,cpus='2-3',coherent_cpus='0-1',
                     optimized_dsp=True,sequence_acquisition=True,optimized_v3=True)
            p.write_text(json.dumps(cfg))
            self.assertFalse(plan(p,info)['config']['optimized_extended'])
            p.write_text(json.dumps({**cfg,'optimized_extended':True}))
            self.assertTrue(plan(p,info)['config']['optimized_extended'])
            p.write_text(json.dumps({**cfg,'optimized_v3':False,'optimized_extended':True}))
            with self.assertRaises(ValueError):plan(p,info)
            p.write_text(json.dumps({**cfg,'coherent_pair_retry':True}))
            self.assertTrue(plan(p,info)['config']['coherent_pair_retry'])
            p.write_text(json.dumps({**cfg,'optimized_v3':False,'coherent_pair_retry':True}))
            with self.assertRaises(ValueError):plan(p,info)
    def test_tuned_config_preserves_cpu_selection_and_rejects_invalid_bounds(self):
        info=dict(logical_cpus=[0,1,2,3],performance_cpus=[0,1,2,3],classification_verified=True)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'workers.json'
            cfg=dict(workers=2,max_workers=2,cpus='2-3',coherent_cpus='0-1',coherent_threshold=.35,coherent_budget=48)
            p.write_text(json.dumps(cfg));s=plan(p,info)
            self.assertEqual(s['worker_cpus'],[2,3]);self.assertEqual(s['coherent_cpus'],[0,1])
            self.assertEqual(s['config']['coherent_budget'],48)
            for k,v in [('coherent_threshold',float('nan')),('coherent_threshold',False),('coherent_budget',48.5),('coherent_budget',257)]:
                p.write_text(json.dumps({**cfg,k:v}))
                with self.assertRaises(ValueError):plan(p,info)

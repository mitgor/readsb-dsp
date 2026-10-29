import os,tempfile,time,unittest
from pathlib import Path
import numpy as np
from rescue.streaming import Assembler,StreamingPool,TOTAL,CORE,RATE,HALO
from rescue.native import iq_blocks,library
from rescue.runtime import RescueDecoder
from rescue.pipeline import settings

class StreamingTests(unittest.TestCase):
    def capture(self,raw,dispatch_ms=100):
        assembler=Assembler(dispatch_ms);batches=[]
        # Actual tap-sized packets with arbitrary boundaries.
        for start in range(0,len(raw)//2,16384):
            batches+=assembler.feed(7,start,start/RATE,raw[start*2:(start+16384)*2])
        return assembler,batches
    def test_emit_before_one_second_with_continuous_phase_and_complete_training_raw(self):
        raw=np.random.default_rng(51).integers(0,256,TOTAL*2,dtype=np.uint8).tobytes()
        for dispatch in (50,100):
            assembler,batches=self.capture(raw,dispatch)
            self.assertEqual(len(batches),1000//dispatch)
            self.assertEqual(batches[0].bounds,(0,dispatch//50))
            self.assertLess(len(batches[0].raw),len(raw)//5)
            self.assertEqual(batches[-1].whole_raw,raw)
            self.assertEqual([b for batch in batches for b in range(*batch.bounds)],list(range(21)))
            self.assertLessEqual(len(assembler.buf),2*HALO*2)
    def test_contiguous_rf_seconds_retain_exact_overlapping_training_windows(self):
        raw=np.random.default_rng(54).integers(0,256,(2*CORE+2*HALO)*2,dtype=np.uint8).tobytes()
        _,batches=self.capture(raw)
        finals=[batch for batch in batches if batch.whole_raw is not None]
        self.assertEqual([batch.first for batch in finals],[0,CORE])
        self.assertEqual(finals[0].whole_raw,raw[:TOTAL*2])
        self.assertEqual(finals[1].whole_raw,raw[CORE*2:(CORE+TOTAL)*2])
    def test_comparison_waits_for_stock_even_after_decoding_finishes(self):
        from collections import deque
        from unittest.mock import patch
        pool=object.__new__(StreamingPool);pool.pending=deque()
        pool.finished=deque([(50.,('rf-second',[],{}))])
        with patch('rescue.streaming.time.monotonic',return_value=49.9):self.assertIsNone(pool.pop())
        with patch('rescue.streaming.time.monotonic',return_value=50.):self.assertEqual(pool.pop()[0],'rf-second')
    def test_gap_and_epoch_change_discard_partial_group_and_preserve_mod_three(self):
        a=Assembler();self.assertEqual(a.feed(1,1,0,b'\x7f'*(1000*2)),[])
        self.assertEqual(a.feed(1,9001,1,b'\x7f'*(1000*2)),[])
        self.assertEqual(a.discontinuities,2);self.assertEqual(a.first%3,0)
        self.assertEqual(a.feed(2,0,2,b'\x7f'*(1000*2)),[])
        self.assertEqual(a.discontinuities,3);self.assertEqual(a.epoch,2)
    def test_streaming_fir_matches_all_serial_samples_at_every_batch_seam(self):
        try:library()
        except OSError:self.skipTest('Build optional native frontend first')
        raw=np.random.default_rng(52).integers(90,165,TOTAL*2,dtype=np.uint8).tobytes()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'iq.uc8';p.write_bytes(raw)
            reference=list(iq_blocks(p))
            for dispatch in (50,100):
                _,batches=self.capture(raw,dispatch);actual=[]
                for batch in batches:
                    p.write_bytes(batch.raw)
                    actual+=list(iq_blocks(p,block_range=batch.bounds,source_first=batch.raw_start,total_samples=TOTAL))
                self.assertEqual(len(actual),len(reference))
                for (offset,core,iq),(expected_offset,expected_core,expected_iq) in zip(actual,reference):
                    self.assertEqual((offset,core),(expected_offset,expected_core));np.testing.assert_array_equal(iq,expected_iq)
                p.write_bytes(raw)
    def test_spawn_stream_matches_serial_and_stock_settling_does_not_delay_dsp(self):
        try:library()
        except OSError:self.skipTest('Build optional native frontend first')
        raw=np.random.default_rng(53).integers(110,145,TOTAL*2,dtype=np.uint8).tobytes()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'reference.uc8';p.write_bytes(raw)
            decoder=RescueDecoder('unused',frontend='native',broad_crc=True,neural=False,methods=('timing','soft','matched'))
            expected,_=decoder.decode(p);_,batches=self.capture(raw)
            allowed=sorted(os.sched_getaffinity(0))[-2:] if hasattr(os,'sched_getaffinity') else []
            pool=StreamingPool('unused',settings(),root,dict(workers=2,worker_cpus=allowed),settle_s=.1)
            try:
                submitted=0;result=None;deadline=time.monotonic()+30
                while result is None and time.monotonic()<deadline:
                    while submitted<len(batches) and len(pool.pending)<pool.max_pending_jobs:
                        pool.submit(batches[submitted]);submitted+=1
                    result=pool.pop();time.sleep(.002)
                self.assertIsNotNone(result);item,events,work=result
                self.assertEqual(events,expected);self.assertEqual(item[3],raw)
                self.assertEqual(work['blocks'],21);self.assertEqual(work['dispatch_ms'],100)
                self.assertEqual(sum(pool.completed.values()),20)
                self.assertEqual(pool.report()['completed_rf_seconds'],1)
                self.assertEqual(pool.report()['incomplete_rf_seconds_shed'],0)
            finally:pool.close()
            self.assertFalse(list(root.glob('job-*.uc8')))
    def test_separate_coherent_pool_matches_serial_and_reports_all_four_roles(self):
        try:library()
        except OSError:self.skipTest('Build optional native frontend first')
        raw=np.random.default_rng(180).integers(110,145,TOTAL*2,dtype=np.uint8).tobytes()
        cpus=sorted(os.sched_getaffinity(0))[:4] if hasattr(os,'sched_getaffinity') else [0,1,2,3]
        if len(cpus)<4:self.skipTest('Four worker affinity CPUs needed')
        if len(cpus)<4:self.skipTest('Four CPUs needed for isolated pools')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'reference.uc8';path.write_bytes(raw)
            decoder=RescueDecoder('unused',frontend='native',broad_crc=True,neural=False,methods=('timing','soft','matched'),coherent=True)
            expected,_=decoder.decode(path);_,batches=self.capture(raw)
            pool=StreamingPool('unused',{**settings(),'coherent':True},root,dict(workers=2,worker_cpus=cpus[2:],coherent_cpus=cpus[:2]),settle_s=0)
            try:
                submitted=0;result=None;deadline=time.monotonic()+40
                while result is None and time.monotonic()<deadline:
                    while submitted<len(batches) and len(pool.pending)<pool.max_pending_jobs:
                        pool.submit(batches[submitted]);submitted+=1
                    result=pool.pop();time.sleep(.002)
                self.assertIsNotNone(result)
                _,events,work=result;self.assertEqual(events,expected)
                self.assertEqual(work['blocks'],21);self.assertEqual(work['coherent_blocks'],21)
                report=pool.report();self.assertEqual(report['coherent_workers'],2)
                self.assertEqual(sorted(report['role_by_pid'].values()),['coherent','coherent','dsp','dsp'])
                if hasattr(os,'sched_getaffinity'):
                    for pid,role in report['role_by_pid'].items():self.assertTrue(set(report['affinity_by_pid'][pid])<=set(cpus[:2] if role=='coherent' else cpus[2:]))
            finally:pool.close()
            self.assertFalse(list(root.glob('job-*.uc8')))
    def test_missing_batch_cannot_inflate_statistics_with_partial_rf_seconds(self):
        pool=object.__new__(StreamingPool);pool.group=None;pool.incomplete_groups=0
        pool.batch_latencies=[];pool.settle_s=0;pool.finished=[]
        _,batches=self.capture(b'\x7f'*(TOTAL*2))
        work=dict(result_latency_s=.01)
        pool._assemble(batches[0],[],work);pool._assemble(batches[2],[],work)
        self.assertIsNone(pool.group);self.assertEqual(pool.incomplete_groups,1)
        for batch in batches[3:]:pool._assemble(batch,[],work)
        self.assertFalse(pool.finished)

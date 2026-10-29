import os,tempfile,time,unittest
from pathlib import Path
import numpy as np
from rescue.ring_transport import RingStreamingPool
from rescue.streaming import Assembler,TOTAL
from rescue.pipeline import settings
class BudgetPoolTests(unittest.TestCase):
 def test_stock_only_needs_no_frontend_consumer_and_recovers(self):
  cpus=sorted(os.sched_getaffinity(0))[:4] if hasattr(os,'sched_getaffinity') else [0,1,2,3]
  if len(cpus)<4:self.skipTest('Four worker affinity CPUs needed')
  cfg=dict(workers=2,worker_cpus=cpus[2:],coherent_cpus=cpus[:2],config=dict(optimized_dsp=True,optimized_v3=True,sequence_acquisition=True,sequence_enabled=False,cached_fir=True))
  root=Path(__file__).resolve().parents[1];raw=np.random.default_rng(34).integers(125,130,2*TOTAL,dtype=np.uint8).tobytes()
  with tempfile.TemporaryDirectory() as tmp:
   pool=RingStreamingPool(root/'models/tiny-fp32.onnx',{**settings(),'coherent':True},Path(tmp),cfg,settle_s=0)
   try:
    for level in (4,0):
     pool.job_policy={'level':level}
     # Start each independent test window at phase zero.
     batches=Assembler().feed(level+1,0,0,raw);i=0;result=None;deadline=time.monotonic()+90
     while result is None and time.monotonic()<deadline:
      while i<len(batches) and len(pool.pending)<pool.max_pending_jobs:pool.submit(batches[i]);i+=1
      result=pool.pop();time.sleep(.001)
     self.assertIsNotNone(result);self.assertEqual(pool.ring.active(),0)
     if level==4:self.assertEqual(result[1],[]);self.assertGreater(result[2]['budget_skipped_jobs'],0)
     else:self.assertNotIn('budget_skipped_jobs',result[2])
   finally:pool.close()

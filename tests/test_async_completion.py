import unittest,sys
from pathlib import Path
from concurrent.futures import Future
sys.path.insert(0,str(Path(__file__).parent))
from rescue.async_completion import CompletionPool
class Tests(unittest.TestCase):
 def test_future_finishes_and_is_removed_inside_grouping(self):
  f=Future()
  class Base:
   def pop(self):f.set_result(([dict(source='energy',sample_4msps=7,message_hex='p')],{}));self.pending.clear();return 'normal'
  class Pool(CompletionPool,Base):pass
  p=Pool();p.pending=[('batch',[f],0,None)];self.assertEqual(p.pop(),'normal');self.assertEqual(p.take_completed()[0][1][0]['sample_4msps'],7)
 def test_ready_future_not_waiting_for_slow_future_and_not_duplicated(self):
  a,b=Future(),Future();a.set_result(([dict(source='energy')],{}))
  class Base:
   def pop(self):return None
  class Pool(CompletionPool,Base):pass
  p=Pool();p.pending=[('batch',[a,b],0,None)];p.pop();self.assertEqual(len(p.take_completed()),1);p.pop();self.assertFalse(p.take_completed());b.set_result(([dict(source='coherent')],{}));p.pop();self.assertEqual(len(p.take_completed()),1)
if __name__=='__main__':unittest.main()

class NativePoolTests(unittest.TestCase):
 def test_actual_native_futures_match_grouped_packets(self):
  import os,tempfile,time
  from rescue.streaming import Assembler,StreamingPool,TOTAL
  from rescue.pipeline import settings
  class Pool(CompletionPool,StreamingPool):pass
  raw=bytes([127,128])*TOTAL
  batches=Assembler(100).feed(1,0,0,raw)
  selection=dict(workers=1,worker_cpus=[],config={})
  with tempfile.TemporaryDirectory() as d:
   pool=Pool('unused',{**settings(),'crc':False},Path(d),selection,settle_s=0)
   try:
    submitted=0;completed=[];result=None;deadline=time.monotonic()+30
    while result is None and time.monotonic()<deadline:
     while submitted<len(batches) and len(pool.pending)<pool.max_pending_jobs:
      pool.submit(batches[submitted]);submitted+=1
     result=pool.pop();completed.extend(pool.take_completed());time.sleep(.002)
    self.assertIsNotNone(result)
    self.assertEqual(len(completed),len(batches))
    self.assertEqual([row for batch,rows,work in completed for row in rows],result[1])
    self.assertEqual(result[1],[])  # DC control must not invent any packet.
   finally:pool.close()

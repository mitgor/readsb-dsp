import unittest,sys
from pathlib import Path
from concurrent.futures import Future
sys.path.insert(0,str(Path(__file__).parent))
from completion import CompletionPool
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

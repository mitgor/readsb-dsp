import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from bridge import Bridge,CompletionPool
from rescue.streaming import Batch
from concurrent.futures import Future
class Tests(unittest.TestCase):
 def batch(self,first=0):return Batch(1,first,0,b'',(0,2),0,0)
 def test_no_global_barrier_and_grouping_intact(self):
  class Base:
   def pop(self):return 'unchanged'
  class Pool(CompletionPool,Base):pass
  p=Pool();done=Future();waiting=Future();done.set_result(([dict(source='energy',sample_4msps=2000,message_hex='a')],{}));p.pending=[(self.batch(),[done,waiting],0,None)]
  self.assertEqual(p.pop(),'unchanged');self.assertEqual(len(p.take_completed()),1);p.pop();self.assertFalse(p.take_completed())
 def test_raw_seam_candidates_are_not_pre_deduplicated(self):
  class Base:
   def pop(self):return None
  class Pool(CompletionPool,Base):pass
  p=Pool();f=Future();rows=[dict(source='energy',sample_4msps=n,message_hex='a') for n in (0,400,800)];f.set_result((rows,{}));p.pending=[(self.batch(),[f],0,None)];p.pop();self.assertEqual(p.take_completed()[0][1],rows)
 def test_watermark_alignment_and_shared_dedup(self):
  b=Bridge(dict(energy=True,coherent=True));rows=[dict(source='energy',sample_4msps=2000,message_hex='a')]
  with patch('bridge.evaluate',return_value=([dict(source='energy',ticks=6000,message_hex='a')],dict(verified=True),{})) as gate:
   b.offer(self.batch(),rows,0);self.assertFalse(b.drain([],None,.1,1200000));self.assertFalse(b.drain([],1,.1,1200000));self.assertFalse(gate.called)
   out=b.drain([],1200000,.1,1200000);self.assertEqual(len(out),1)
   b.offer(self.batch(),rows,.1);self.assertFalse(b.drain([],1200000,.2,1200000))
 def test_out_of_order_completions_not_discarded(self):
  b=Bridge(dict(coherent=True));b.offer(self.batch(240000),[],0);b.offer(self.batch(0),[],0)
  with patch('bridge.evaluate',return_value=([],dict(verified=True),{})) as gate:b.drain([],99999999,.1,99999999);self.assertEqual(gate.call_count,2)
 def test_late_pending_keeps_its_causal_anchor_window(self):
  b=Bridge(dict(energy=True));b.offer(self.batch(),[dict(source='energy',sample_4msps=2000,message_hex='a')],0)
  with patch('bridge.evaluate',return_value=([],dict(verified=True),{})) as gate:
   b.drain([],24000000,.2,24000000);self.assertEqual(len(gate.call_args.args[1]),1)
 def test_actual_admission_crc_unknown_address_and_conflict(self):
  from rescue.stock_history import StockHistory
  from rescue.shadow import valid_df17
  p='8d40621d58c382d690c8ac2863a7';q='8d40621d58c386435cc412692ad6';unknown='8d4840d6202cc371c32ce0576098'
  self.assertTrue(all(valid_df17(x) for x in (p,q,unknown)))
  h=StockHistory();rows=[]
  for i in range(20):
   sample=4000+i*2000;t=sample*3;h.append(dict(ticks=t,message_hex=p));rows.append(dict(source='energy',sample_4msps=sample,message_hex=p))
  rows += [dict(source='coherent',sample_4msps=60000,message_hex=q),dict(source='coherent',sample_4msps=62000,message_hex=unknown),dict(source='coherent',sample_4msps=64000,message_hex=q[:-1]+'0')]
  b=Bridge(dict(energy=True,coherent=True));b.offer(self.batch(),rows,0);sent=b.drain(h.snapshot(),1200000,.1,1200000)
  self.assertEqual([r['message_hex'] for r in sent],[q]);self.assertGreater(b.count['no_prior_stock_icao'],0);self.assertGreater(b.count['invalid'],0)
  # Same RF instant with a conflicting stock payload must veto that extra.
  h.append(dict(ticks=180000,message_hex=p));b=Bridge(dict(energy=True,coherent=True));b.offer(self.batch(),rows,0);self.assertFalse(b.drain(h.snapshot(),1200000,.1,1200000));self.assertGreater(b.count['stock_conflict'],0)
 def test_late_old_epoch_cannot_reset_current_input_epoch(self):
  b=Bridge(dict(energy=True));b.begin_epoch(2);b.offer(self.batch(),[],0);self.assertEqual(b.epoch,2);self.assertFalse(b.pending);self.assertEqual(b.count['wrong_epoch'],1)
 def test_sink_preserves_clock_epoch_source_and_audit(self):
  from bridge import publish_to
  class Hub:
   def submit(self,source,batch):self.source=source;self.batch=batch;return True
  h=Hub();r=dict(source='coherent',epoch=7,ticks=1000,message_hex='a',alignment=dict(verified=True,matches=20,median_abs_error_us=0))
  self.assertEqual(publish_to(h,[r],123),dict(queued=1));self.assertEqual(h.source,'coherent');self.assertEqual(h.batch['extra'][0]['ticks'],1000);self.assertEqual(h.batch['admission'],'production_guarded_v1');self.assertEqual(h.batch['epoch'],7)
 def test_unverified_does_not_emit(self):
  b=Bridge(dict(energy=True));b.offer(self.batch(),[],0)
  with patch('bridge.evaluate',return_value=([],dict(verified=False),{})):self.assertFalse(b.drain([],1200000,.1,1200000))
  self.assertEqual(len(b.pending),1);b.drain([],1200000,4,1200000);self.assertFalse(b.pending)
if __name__=='__main__':unittest.main()

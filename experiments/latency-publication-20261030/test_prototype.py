import sys,unittest
from pathlib import Path
from history import HistoryMerge
from prototype import SmallBatchGate,ImmediateRelay,BatchTap
from rescue.feed import beast,Records,CORRECTION,MOD
from rescue.wire import BeastParser
from rescue.streaming import Batch,StreamingPool
from rescue.shadow import evaluate

def payload(n):
 v=int('8d40621d58c382d690c8ac',16)^(n<<8);a=v<<24;r=a
 for b in range(111,23,-1):
  if r&(1<<b):r^=0x1fff409<<(b-24)
 return (a|r).to_bytes(14,'big').hex()
def frame(p,t):return BeastParser().feed(beast(p,t))[0]
class Tests(unittest.TestCase):
 def test_stock_immediate_opaque_and_timestamp_wrap(self):
  r=ImmediateRelay(HistoryMerge);p=payload(0)
  for t in (MOD-100,500):
   w=beast(p,t);r.stock(w,frame(p,t),1,epoch=7);self.assertEqual(r.ready(1),w)
  r.stock(b'opaque',None,1,epoch=7);self.assertEqual(r.ready(1),b'opaque')
 def test_repeated_payload_dedup_disabled_age_and_epoch_guards(self):
  r=ImmediateRelay(HistoryMerge);p,q=payload(0),payload(1)
  r.stock(beast(p,10000),frame(p,10000),1,epoch=7);r.ready(1)
  r.stock(beast(p,1200000),frame(p,1200000),1.1,epoch=7);r.ready(1.1)
  def batch(t,source='energy',epoch=7):return dict(epoch=epoch,created_unix=2,alignment={'verified':True},extra=[dict(message_hex=q,ticks=t-CORRECTION,source=source)])
  r.batch(batch(600000),1.1,2,{'energy':True});self.assertTrue(r.ready(1.1))
  r.batch(batch(600000,'matched'),1.11,2,{'matched':True});self.assertFalse(r.ready(1.11))
  r.batch(batch(700000),1.12,2,{'energy':False});self.assertFalse(r.ready(1.12))
  r.batch(batch(800000,epoch=8),1.12,2,{'energy':True});self.assertFalse(r.ready(1.12))
  r.batch(batch(900000),1.12,2.3,{'energy':True});self.assertFalse(r.ready(1.12))
  r.batch(batch(1500000),1.12,2,{'energy':True});self.assertFalse(r.ready(1.12))
  r.batch(batch(1000000),1.13,2,{'energy':True});self.assertTrue(r.ready(1.13))
 def test_late_stock_always_preserved_and_race_visible(self):
  r=ImmediateRelay(HistoryMerge);p,q=payload(0),payload(1)
  r.stock(beast(p,10000),frame(p,10000),1,epoch=7);r.stock(beast(p,1200000),frame(p,1200000),1.1,epoch=7);r.ready(1.1)
  r.batch(dict(epoch=7,created_unix=2,alignment={'verified':True},extra=[dict(message_hex=q,ticks=600000-CORRECTION,source='energy')]),1.1,2,{'energy':True});self.assertTrue(r.ready(1.1))
  w=beast(q,600000);r.stock(w,frame(q,600000),1.2,epoch=7);self.assertEqual(r.ready(1.2),w);self.assertEqual(r.cache.count['late_stock_after_extra_race'],1)
 def data(self):
  rows=[dict(source='energy',message_hex=payload(0),sample_4msps=2000+20000*i) for i in range(20)]
  rows.append(dict(source='matched',message_hex=payload(1),sample_4msps=390000))
  frames=[dict(ticks=r['sample_4msps']*3,message_hex=r['message_hex']) for r in rows[:-1]]
  b=Batch(7,0,0,b'',(0,2),0,1)
  return b,rows,frames
 def test_batch_gates_match_current_admission_with_watermark(self):
  b,rows,frames=self.data();g=SmallBatchGate();g.offer(b,rows,1)
  self.assertFalse(g.drain(frames,1.1,7,100,{'energy':True,'matched':True}))
  out=g.drain(frames,1.12,7,1200000,{'energy':True,'matched':True});self.assertEqual(len(out),1)
  expected,_,_=evaluate(frames,[{**r,'ticks':r['sample_4msps']*3} for r in rows],3000,1200000)
  self.assertEqual(out[0]['extra'],expected);self.assertEqual(len(expected),1)
 def test_unaligned_expired_or_wrong_epoch_fail_closed(self):
  b,rows,frames=self.data()
  for kind in ('unaligned','expired','epoch'):
   g=SmallBatchGate();g.offer(b,rows,1)
   out=g.drain(frames[:5] if kind=='unaligned' else frames,1.3 if kind=='expired' else 1.1,8 if kind=='epoch' else 7,1200000,{'energy':True,'matched':True})
   self.assertFalse(out if kind!='unaligned' else [r for r in out if r['extra']])
 def test_tap_preserves_one_second_assembly(self):
  from unittest.mock import patch
  class Tapped(BatchTap,StreamingPool):pass
  pool=object.__new__(Tapped);b,rows,_=self.data()
  with patch.object(StreamingPool,'_assemble',return_value='original') as original:
   self.assertEqual(pool._assemble(b,rows,{}),'original');original.assert_called_once_with(b,rows,{})
  early=pool.pop_batches();self.assertEqual(len(early),1);self.assertEqual(len(early[0][1]),21);self.assertFalse(pool.pop_batches())
 def test_closed_source_epoch_discards_identity(self):
  r=ImmediateRelay(HistoryMerge);p=payload(0);r.stock(beast(p,10000),frame(p,10000),1,epoch=1);r.ready(1)
  r.stock(beast(payload(2),20000),frame(payload(2),20000),2,epoch=2)
  self.assertEqual(list(r.history),[(20000,payload(2))]);self.assertEqual(r.cache.epoch,2)
if __name__=='__main__':unittest.main()

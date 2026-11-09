import unittest,asyncio,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from integration import SourceHub,Admission,SOURCES
from rescue.feed import beast,CORRECTION
from rescue.wire import BeastParser
from rescue.stock_history import StockHistory
from rescue.streaming import Batch
P='8d40621d58c382d690c8ac2863a7';Q='8d40621d58c386435cc412692ad6';audit=dict(verified=True,matches=20,median_abs_error_us=0)
class Tests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.now=1.;self.rows=[];self.h=SourceHub({s:True for s in SOURCES},clock=lambda:self.now,sink=lambda b,s,t:self.rows.extend((s,f) for f in BeastParser().feed(b)));self.h.start();self.h.begin_epoch(8)
  for t in [0,1200000]:
   raw=beast(P,t+CORRECTION);self.h.stock(raw,BeastParser().feed(raw)[0],8)
  self.rows=[]
 async def asyncTearDown(self):await self.h.close()
 async def test_all_sources_share_one_cache(self):
  for s in SOURCES:self.h.submit(s,8,[dict(source=s,ticks=600000,message_hex=Q)],audit)
  await self.h.settle();self.assertEqual(len(self.rows),1);self.assertEqual(self.h.relay.cache.count['cross_stream_duplicate_rejected'],len(SOURCES)-1)
 async def test_repeat_later_transmission_kept(self):
  self.h.submit('pulse',8,[dict(source='pulse',ticks=600000,message_hex=Q),dict(source='pulse',ticks=620000,message_hex=Q)],audit);await self.h.settle();self.assertEqual(len(self.rows),2)
 async def test_epoch_old_and_unverified_quarantined(self):
  self.assertFalse(self.h.submit('neural',7,[dict(source='neural',ticks=1,message_hex=Q)],audit));self.assertFalse(self.h.submit('broad_crc',8,[],audit));self.assertFalse(self.h.submit('neural',8,[],dict(verified=False)));await self.h.settle();self.assertFalse(self.rows)
 async def test_epoch_change_drops_queued_old_results(self):
  self.h.submit('pulse',8,[dict(source='pulse',ticks=600000,message_hex=Q)],audit);self.h.begin_epoch(9);await self.h.settle();self.assertFalse(self.rows)
 async def test_slow_unsubmitted_source_never_blocks_ready_source(self):
  self.h.submit('energy',8,[dict(source='energy',ticks=600000,message_hex=Q)],audit);await asyncio.wait_for(self.h.settle(),1);self.assertEqual(len(self.rows),1)
 async def test_original_stock_survives_late_duplicate(self):
  self.h.submit('energy',8,[dict(source='energy',ticks=600000,message_hex=Q)],audit);await self.h.settle();raw=beast(Q,600000+CORRECTION);self.h.stock(raw,BeastParser().feed(raw)[0],8);self.assertEqual(len(self.rows),2);self.assertEqual(self.rows[-1][0],'stock');self.assertEqual(self.h.relay.cache.count['late_stock_after_extra_race'],1)
 async def test_corrupt_and_unknown_address_rejected(self):
  self.h.submit('energy',8,[dict(source='energy',ticks=600000,message_hex=Q[:-1]+'0')],audit);self.h.submit('neural',8,[dict(source='neural',ticks=600000,message_hex='8d4840d6202cc371c32ce0576098')],audit);await self.h.settle();self.assertFalse(self.rows)
 async def test_receiver_restart_clears_admission_anchors(self):
  a=Admission(self.h);a.energy[(1,P)]=dict(ticks=1,message_hex=P);a.pending.append((8,0,100,[],0,None));self.h.begin_epoch(9);a.drain([],None,self.now);self.assertFalse(a.energy);self.assertFalse(a.pending);self.assertEqual(a.epoch,9)
 async def test_stream_adapter_admits_same_raw_clock(self):
  a=Admission(self.h);frames=StockHistory();events=[]
  for i in range(20):
   sample=4000+i*2000;frames.append(dict(ticks=sample*3,message_hex=P));events.append(dict(source='energy',sample_4msps=sample,message_hex=P))
  a.offer(Batch(8,0,0,b'',(0,2),0,0),events,self.now);a.offer_stream1090(8,0,[dict(source='stream1090',ticks=180000,message_hex=Q)],self.now)
  a.drain(frames.snapshot(),12012000,self.now);await self.h.settle();self.assertEqual([s for s,r in self.rows],['stream1090'])
if __name__=='__main__':unittest.main()

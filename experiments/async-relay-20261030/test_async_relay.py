import asyncio,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import Future
from types import SimpleNamespace as NS
from async_relay import AsyncFanIn,Subscriber,SOURCES,serve
from completion_tap import CompletionTap
from dedup import HistoryMerge
from rescue.feed import beast,CORRECTION
from rescue.wire import BeastParser

def payload(n):
 value=int('8d40621d58c382d690c8ac',16)^(n<<8);v=value<<24;r=v
 for bit in range(111,23,-1):
  if r&(1<<bit):r^=0x1fff409<<(bit-24)
 return (v|r).to_bytes(14,'big').hex()
def frame(p,t):return BeastParser().feed(beast(p,t))[0]
def batch(source,t=600000,n=1):return dict(epoch=7,created_unix=time.time(),admission='production_guarded_v1',alignment=dict(verified=True,matches=20,median_abs_error_us=1),extra=[dict(message_hex=payload(n),ticks=t-CORRECTION,source=source)])
class Writer:
 def __init__(self,stall=False):self.raw=bytearray();self.stall=stall;self.closed=False
 def write(self,raw):self.raw.extend(raw)
 async def drain(self):
  if self.stall:await asyncio.sleep(10)
 def close(self):self.closed=True

class AsyncTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.enabled={s:True for s in SOURCES};self.hub=AsyncFanIn(lambda:self.enabled);self.hub.start();self.writer=Writer();self.sub=Subscriber(self.writer,self.hub);self.hub.clients.add(self.sub)
  self.hub.stock(beast(payload(0),10000),frame(payload(0),10000),7);self.hub.stock(beast(payload(0),1200000),frame(payload(0),1200000),7);await asyncio.wait_for(self.sub.queue.join(),2);self.writer.raw.clear()
 async def asyncTearDown(self):await self.hub.close()
 async def settle(self):
  await asyncio.wait_for(asyncio.gather(*(q.join() for q in self.hub.queues.values())),2);await asyncio.wait_for(self.sub.queue.join(),2)
 async def test_all_sources_deliver_without_waiting_for_other_streams(self):
  for i,s in enumerate(sorted(SOURCES)):self.assertTrue(self.hub.submit(s,batch(s,400000+i*10000,i+1)))
  await self.settle();frames=BeastParser().feed(bytes(self.writer.raw));self.assertEqual(len(frames),len(SOURCES));self.assertEqual(sum(self.hub.count['emitted_'+s] for s in SOURCES),len(SOURCES))
 async def test_slow_absent_neural_does_not_delay_energy_or_stock(self):
  never=asyncio.Event()
  async def neural():await never.wait()
  task=asyncio.create_task(neural())
  try:
   self.hub.submit('energy',batch('energy'));wire=beast(payload(2),1300000);self.hub.stock(wire,frame(payload(2),1300000),7);await self.settle()
   out=bytes(self.writer.raw);self.assertIn(wire,out);self.assertEqual(self.hub.count['emitted_energy'],1)
  finally:task.cancel();await asyncio.gather(task,return_exceptions=True)
 async def test_shared_duplicate_cache_and_legitimate_repeat(self):
  self.hub.submit('energy',batch('energy'));self.hub.submit('coherent',batch('coherent'));await self.settle()
  self.assertEqual(len(BeastParser().feed(bytes(self.writer.raw))),1)
  self.hub.submit('matched',batch('matched',700000));await self.settle();self.assertEqual(len(BeastParser().feed(bytes(self.writer.raw))),2)
 async def test_disabled_quarantined_and_cross_channel_spoof_rejected(self):
  self.enabled['neural']=False;self.hub.submit('neural',batch('neural'));self.assertFalse(self.hub.submit('broad_crc',batch('broad_crc')))
  self.hub.submit('energy',batch('coherent'));self.hub.submit('matched',{'extra':[None]});await self.settle();self.assertFalse(self.writer.raw)
 async def test_expired_bad_alignment_wrong_epoch_and_conflict(self):
  for change in [{'created_unix':time.time()-1},{'epoch':8},{'alignment':dict(verified=True,matches=19,median_abs_error_us=1)},{'alignment':dict(verified=True,matches=20,median_abs_error_us=3)}]:
   b=batch('energy');b.update(change);self.hub.submit('energy',b)
  self.hub.stock(beast(payload(2),600000),frame(payload(2),600000),7);self.writer.raw.clear()
  self.hub.submit('matched',batch('matched'));await self.settle()
  # Only the original stock byte survives; no experimental output.
  frames=BeastParser().feed(bytes(self.writer.raw));self.assertTrue(all(f['message_hex']==payload(2) for f in frames));self.assertFalse(self.hub.count['emitted_matched'])
 async def test_slow_subscriber_cannot_block_good_consumer(self):
  slow=Writer(stall=True);s=Subscriber(slow,self.hub,timeout=.01);self.hub.clients.add(s)
  wire=beast(payload(3),1400000);self.hub.stock(wire,frame(payload(3),1400000),7);await asyncio.sleep(.04)
  self.assertTrue(slow.closed);self.assertIn(wire,self.writer.raw);self.assertFalse(self.writer.closed)
 async def test_finite_server_real_tcp_and_unix_ipc(self):
  async def source(reader,writer):
   try:
    for i in range(100):
     writer.write(beast(payload(0),1200000+i*10000));await writer.drain();await asyncio.sleep(.02)
   except ConnectionError:pass
   finally:writer.close()
  upstream=await asyncio.start_server(source,'127.0.0.1',0)
  with tempfile.TemporaryDirectory(dir='/tmp',prefix='async-relay-test-') as d:
   p=Path(d);(p/'switch.json').write_text(json.dumps(self.enabled));runtime=p/'r';task=asyncio.create_task(serve(NS(port=0,runtime=runtime,switches=p/'switch.json',stock_port=upstream.sockets[0].getsockname()[1],seconds=1.5)));writer=producer=None
   try:
    for _ in range(60):
     if (runtime/'endpoint.json').exists():break
     await asyncio.sleep(.005)
    meta=json.loads((runtime/'endpoint.json').read_text());reader,writer=await asyncio.open_connection(meta['host'],meta['port']);parser=BeastParser()
    # An observed stock packet proves the relay has an anchor/identity; do not
    # assume ordering between endpoint publication, TCP connect and upstream.
    observed=[]
    while len(observed)<2:observed.extend(parser.feed(await asyncio.wait_for(reader.read(4096),2)))
    _,producer=await asyncio.open_unix_connection(meta['ipc']);b=batch('energy');b['epoch']=1;b['extra'][0]['ticks']=(observed[-2]['ticks_12mhz']+observed[-1]['ticks_12mhz'])//2-CORRECTION;producer.write((json.dumps(dict(producer='energy',batch=b))+'\n').encode());await producer.drain();found=False
    for _ in range(100):
     data=await asyncio.wait_for(reader.read(4096),2)
     if not data:break
     if any(f['message_hex']==payload(1) for f in parser.feed(data)):found=True;break
    self.assertTrue(found,'IPC extra absent from test output')
   finally:
    if producer:producer.close()
    if writer:writer.close()
    await asyncio.wait_for(task,3)
    upstream.close();await upstream.wait_closed()
   self.assertTrue((runtime/'final.json').exists());self.assertFalse((runtime/'ipc.sock').exists())

class Tests(unittest.TestCase):
 def test_ttl_capacity_and_rf_event_identity(self):
  m=HistoryMerge(capacity=2);m.push('stock',1,10000,'a',1);m.push('stock',1,20000,'b',1);m.push('stock',1,30000,'c',1);self.assertEqual(m.serial_count,2);self.assertEqual(m.count['capacity_evictions'],1);m.prune(7);self.assertFalse(m.index)
 def test_completed_cheap_future_visible_while_coherent_pending(self):
  class Base:
   def pop(self):return 'original_unchanged'
  class Tapped(CompletionTap,Base):pass
  cheap=Future();slow=Future();cheap.set_result(([dict(source='energy',sample_4msps=10,message_hex=payload(1))],{}));obj=Tapped();obj.pending=[(NS(epoch=7,first=0,queued=1),[cheap,slow],0,Path('/tmp/owned'))]
  self.assertEqual(obj.pop(),'original_unchanged');r=obj.pop_methods();self.assertEqual(r[0]['source'],'energy');self.assertFalse(r[0]['admitted']);self.assertFalse(slow.done());obj.pop();self.assertFalse(obj.pop_methods());slow.set_result(([dict(source='coherent',sample_4msps=10,message_hex=payload(2))],{}));obj.pop();self.assertEqual(obj.pop_methods()[0]['source'],'coherent')
if __name__=='__main__':unittest.main()

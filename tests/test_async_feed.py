import unittest,tempfile,json,time,sys,asyncio,hashlib
from pathlib import Path
from unittest.mock import patch
from rescue.async_feed import Relay
from rescue.async_engine import Outbox,Engine,SOURCES
from rescue.feed import beast,CORRECTION,Records
from rescue.wire import BeastParser
from rescue.streaming import Batch
P='8d40621d58c382d690c8ac2863a7';Q='8d40621d58c386435cc412692ad6'
A=dict(verified=True,matches=20,median_abs_error_us=0)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.config=Path(self.tmp.name)/'methods.json';self.config.write_text(json.dumps(dict(energy=True,neural=True,pulse=True,sic=False)));self.r=Relay(self.config)
  for t in [0,1200000]:
   raw=beast(P,t+CORRECTION);self.r.stock(raw,BeastParser().feed(raw)[0],1);self.assertEqual(self.r.ready(1),raw)
 def tearDown(self):self.tmp.cleanup()
 def send(self,source='energy',epoch=8,**kw):
  d=dict(admission='production_guarded_v1',epoch=epoch,producer=source,created_unix=1,alignment=A,extra=[dict(source=source,ticks=600000,message_hex=Q)]);d.update(kw);self.r.batch(d,1,1);return self.r.ready(1)
 def test_common_cache_and_later_repeat(self):
  self.assertTrue(self.send());self.assertFalse(self.send('pulse'));self.assertFalse(self.send('neural'))
  self.assertTrue(self.send(extra=[dict(source='energy',ticks=620000,message_hex=Q)]))
 def test_sic_and_broad_crc_never_forward(self):self.assertFalse(self.send('sic'));self.assertFalse(self.send('broad_crc'))
 def test_epoch_and_contract(self):
  self.assertTrue(self.send());self.assertFalse(self.send(epoch=9));self.assertFalse(self.send(admission='bad'));self.assertFalse(self.send(alignment=dict(verified=True,matches=19,median_abs_error_us=0)))
 def test_stock_after_extra_preserved(self):
  self.assertTrue(self.send());raw=beast(Q,600000+CORRECTION);self.r.stock(raw,BeastParser().feed(raw)[0],1);self.assertEqual(self.r.ready(1),raw);self.assertEqual(self.r.cache.count['late_stock_after_extra_race'],1)
 def test_sequence_acquisition_follow_worker_switches(self):
  self.r.worker_config=Path('/etc/default/adsb-rescue-workers.json')
  original=Path.read_text
  def read(p,*a,**k):return json.dumps(dict(sequence_acquisition=True,sequence_enabled=True,acquisition_enabled=True)) if str(p)=='/etc/default/adsb-rescue-workers.json' else original(p,*a,**k)
  originalexists=Path.exists
  with patch.object(Path,'read_text',read),patch.object(Path,'exists',lambda p:True if str(p)=='/etc/default/adsb-rescue-workers.json' else originalexists(p)):
   self.assertTrue(self.send('sequence'));self.assertFalse(self.send('acquisition'))
 def test_lossless_split_stock_and_opaque(self):
  raw=b'opaque'+beast(P,100+CORRECTION)+b'\x1a4abcd'+beast(P,200+CORRECTION);parser=Records();out=b''
  for v in raw:
   for wire,f in parser.feed(bytes([v])):self.r.stock(wire,f,1);out+=self.r.ready(1)
  out+=bytes(parser.buffer);self.assertEqual(raw,out)
 def test_bound_outbox_and_disabled(self):
  o=Outbox(Path(self.tmp.name)/'outbox',dict(energy=True,sic=False));o.epoch=8
  self.assertTrue(o.submit('energy',8,[],A));self.assertFalse(o.submit('sic',8,[],A));self.assertFalse(o.submit('energy',9,[],A))
class BurstTests(unittest.IsolatedAsyncioTestCase):
 async def test_large_stock_burst_does_not_starve_subscribers(self):
  import socket
  from types import SimpleNamespace
  from rescue.async_feed import run
  raw=b''.join(beast(P,i*3000+CORRECTION) for i in range(6000));gate=asyncio.Event();end=asyncio.Event()
  async def source(reader,writer):
   await gate.wait();writer.write(raw);await writer.drain();await end.wait();writer.close()
  upstream=await asyncio.start_server(source,'127.0.0.1',0)
  probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
  with tempfile.TemporaryDirectory() as d:
   path=Path(d);cfg=path/'cfg';cfg.write_text(json.dumps(dict(energy=True,sic=False)))
   a=SimpleNamespace(config=cfg,runtime=path,stock_port=upstream.sockets[0].getsockname()[1],port=port);task=asyncio.create_task(run(a));writer=None
   try:
    for i in range(100):
     try:reader,writer=await asyncio.open_connection('127.0.0.1',port);break
     except OSError:await asyncio.sleep(.01)
    self.assertIsNotNone(writer);gate.set();received=await asyncio.wait_for(reader.readexactly(len(raw)),5);self.assertEqual(received,raw)
   finally:
    end.set()
    if writer:writer.close();await writer.wait_closed()
    task.cancel();await asyncio.gather(task,return_exceptions=True)
  upstream.close();await upstream.wait_closed()
if __name__=='__main__':unittest.main()

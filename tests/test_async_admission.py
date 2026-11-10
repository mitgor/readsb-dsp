import json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from rescue.async_engine import Engine
from rescue.async_feed import Relay
from rescue.feed import beast,CORRECTION
from rescue.wire import BeastParser
P='8d40621d58c382d690c8ac2863a7';Q='8d40621d58c386435cc412692ad6'
class AdmissionTests(unittest.TestCase):
 def test_worker_completion_to_outbox_to_relay_preserves_one_extra(self):
  frames=[dict(ticks=12000+i*24000,message_hex=P) for i in range(20)]
  frames.append(dict(ticks=1300002,message_hex=P))
  class Live:
   def snapshot(self):return frames,dict(aircraft_unix=time.time())
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);cfg=root/'methods.json';cfg.write_text(json.dumps(dict(energy=True,coherent=True,crc=False)))
   engine=Engine(Live(),root/'feed-outbox',dict(energy=True,coherent=True))
   batch=SimpleNamespace(epoch=7,first=0,bounds=(0,2));engine.begin(batch)
   anchors=[dict(source='energy',sample_4msps=f['ticks']//3,message_hex=P) for f in frames[:-1]]
   extra=dict(source='energy',sample_4msps=600000//3,message_hex=Q)
   engine.offer(batch,anchors+[extra],{});engine.tick()
   paths=list((root/'feed-outbox').glob('*.json'));self.assertEqual(len(paths),1)
   relay=Relay(cfg)
   for f in frames:
    raw=beast(f['message_hex'],f['ticks']+CORRECTION);relay.stock(raw,BeastParser().feed(raw)[0],time.monotonic());self.assertEqual(relay.ready(time.monotonic()),raw)
   relay.batch(json.loads(paths[0].read_text()),time.monotonic(),time.time())
   decoded=BeastParser().feed(relay.ready(time.monotonic()));self.assertEqual([f['message_hex'] for f in decoded],[Q])
   # A later completed producer finds the same RF transmission: no duplicate.
   engine.offer(batch,[{**extra,'source':'coherent'}],{});engine.last_tick=0;engine.tick()
   for path in (root/'feed-outbox').glob('*.json'):
    relay.batch(json.loads(path.read_text()),time.monotonic(),time.time())
   self.assertEqual(relay.ready(time.monotonic()),b'')
 def test_missing_stock_alignment_does_not_authorize_output(self):
  class Live:
   def snapshot(self):return [dict(ticks=1300002,message_hex=P)],dict(aircraft_unix=time.time())
  with tempfile.TemporaryDirectory() as d:
   engine=Engine(Live(),Path(d)/'out',dict(energy=True));batch=SimpleNamespace(epoch=1,first=0,bounds=(0,2))
   engine.begin(batch);engine.offer(batch,[dict(source='energy',sample_4msps=200000,message_hex=Q)],{});engine.tick()
   self.assertFalse(list(Path(d).rglob('*.json')))

class ReceiverContextTests(unittest.TestCase):
 def test_installed_receiver_json_directory_supplies_health(self):
  from rescue.shadow import LiveInput
  from unittest.mock import patch
  with tempfile.TemporaryDirectory(dir='/tmp') as d:
   root=Path(d);(root/'aircraft.json').write_text(json.dumps(dict(now=123456,aircraft=[])))
   (root/'stats.json').write_text('{}')
   live=LiveInput(root/'iq.sock',(52,13),readsb_json=root)
   try:
    with patch.object(live.stop,'wait',side_effect=lambda seconds:live.stop.set()):live.context()
    self.assertEqual(live.health['aircraft_unix'],123456)
    self.assertEqual(live.count['context_errors'],0)
   finally:live.close()

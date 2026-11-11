import json,tempfile,time,unittest
from pathlib import Path
from rescue.relay_control import RelayControls
class RelayTests(unittest.TestCase):
 def test_revision_noop_switch_and_failure(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);cfg=r/'adsb-relay-arrival.json';cfg.write_text('{"enabled":true}');state=r/'active.json';state.write_text('{"state":"active"}');feed=r/'feed-status.json'
   feed.write_text(json.dumps(dict(holdback_s=0,updated_unix=time.time())));(r/'status.json').write_text('{"lowlatency":{"backend":"incremental_native"}}');calls=[]
   def switch(mode):
    calls.append(mode)
    for path,value in [(cfg,dict(enabled=mode=='arrival_order')),(feed,dict(holdback_s=0 if mode=='arrival_order' else 3,updated_unix=time.time()))]:
     tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value));tmp.replace(path)
   control=RelayControls(r,r,state,switch);v=control.read();control.apply(dict(revision=v['revision'],mode='arrival_order'));self.assertFalse(calls)
   with self.assertRaises(ValueError):control.apply(dict(revision='old',mode='ordered_3s'))
   with self.assertRaises(ValueError):control.apply(dict(revision=v['revision'],mode='shell command'))
   control.apply(dict(revision=v['revision'],mode='ordered_3s'))
   for _ in range(100):
    if control.operation['state']!='applying':break
    time.sleep(.01)
   self.assertEqual(control.operation['state'],'complete');self.assertEqual(calls,['ordered_3s']);self.assertEqual(control.read()['actual_holdback_s'],3)
   with self.assertRaises(ValueError):control.apply(dict(revision=v['revision'],mode='arrival_order'))
   control.switch=lambda _:(_ for _ in ()).throw(RuntimeError('test health failure'));control.apply(dict(revision=control.read()['revision'],mode='arrival_order'))
   for _ in range(100):
    if control.operation['state']!='applying':break
    time.sleep(.01)
   self.assertEqual(control.operation['state'],'failed');self.assertEqual(control.read()['actual_holdback_s'],3)
 def test_portable_incremental_imports(self):
  from rescue.lowlatency_stream import TimedDecoder
  from rescue.latency_core.completion_bridge import Bridge
  self.assertTrue(TimedDecoder and Bridge)
 def test_http_rejects_cross_origin(self):
  import threading,urllib.request,urllib.error
  from http.server import ThreadingHTTPServer
  from types import SimpleNamespace
  from rescue.web_control import Handler
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'adsb-relay-arrival.json').write_text('{"enabled":true}');(r/'active.json').write_text('{"state":"active"}');(r/'feed-status.json').write_text(json.dumps(dict(holdback_s=0,updated_unix=time.time())))
   relay=RelayControls(r,r,r/'active.json',lambda _:None);server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.controls=SimpleNamespace(relay=relay,lock=__import__('threading').Lock(),operation={'state':'idle'});thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url='http://127.0.0.1:'+str(server.server_port)
   try:
    state=json.load(urllib.request.urlopen(url+'/readsb-dsp/api/relay'));body=json.dumps(dict(mode='arrival_order',revision=state['revision'])).encode()
    def post(origin):return urllib.request.urlopen(urllib.request.Request(url+'/readsb-dsp/api/relay',data=body,headers={'Content-Type':'application/json','Origin':origin}))
    with self.assertRaises(urllib.error.HTTPError) as e:post('http://other.invalid')
    self.assertEqual(e.exception.code,403);self.assertEqual(json.load(post(url))['actual_holdback_s'],0)
   finally:server.shutdown();server.server_close();thread.join(3)

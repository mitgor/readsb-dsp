import json, threading, unittest, urllib.request
from http.server import ThreadingHTTPServer
from rescue.web_control import Handler
class WebPrefixTests(unittest.TestCase):
 def test_canonical_and_legacy_controls_share_same_read_endpoint(self):
  class Controls:
   def read(self):return {'revision':'same','methods':{}}
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.controls=Controls()
  t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
  try:
   for prefix in ('readsb-dsp','neural-rescue'):
    with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/{prefix}/api/settings') as r:
     self.assertEqual(json.load(r),Controls().read())
  finally:server.shutdown();server.server_close();t.join()

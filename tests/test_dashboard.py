import json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from dataclasses import asdict
from deadsb.dashboard import create_server
from deadsb.governor import Config
class DashboardTests(unittest.TestCase):
 def test_budget_revision_origin_and_validation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);cfg=root/'budget.json';cfg.write_text(json.dumps(asdict(Config())))
   server=create_server(root,cfg,0);t=threading.Thread(target=server.serve_forever,daemon=True);t.start();base='http://127.0.0.1:'+str(server.server_port)
   try:
    d=json.load(urllib.request.urlopen(base+'/api/status'));self.assertEqual(d['status'],{})
    body={'revision':d['revision'],'config':{**d['config'],'target_percent':50}}
    def post(origin):return urllib.request.urlopen(urllib.request.Request(base+'/api/budget',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':origin}),timeout=5)
    with self.assertRaises(urllib.error.HTTPError) as e:post('http://evil.example')
    self.assertEqual(e.exception.code,403)
    self.assertTrue(json.load(post(base))['saved']);self.assertEqual(json.loads(cfg.read_text())['target_percent'],50)
    with self.assertRaises(urllib.error.HTTPError) as e:post(base)
    self.assertEqual(e.exception.code,409)
    body['revision']=json.load(urllib.request.urlopen(base+'/api/status'))['revision'];body['config']['ceiling_percent']=30
    with self.assertRaises(urllib.error.HTTPError) as e:post(base)
    self.assertEqual(e.exception.code,409);self.assertEqual(json.loads(cfg.read_text())['ceiling_percent'],60)
   finally:server.shutdown();server.server_close();t.join(5)

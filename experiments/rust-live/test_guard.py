"""No service access: fault-injection tests for rollback and the watchdog."""
import copy,importlib.util,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('rust_mode',Path(__file__).resolve().parents[2]/'tools/rust_coherent_mode.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def snapshot():
 return {'started_unix':1,'updated_unix':999,'feed_updated_unix':999,'threads_alive':True,'feed':{'stock_connected':True,'fr24_routed':True,'counts':{'stock_bytes_relayed':100}},'fr24':{'feed_status':'connected','rx_connected':'1','feed_last_ac_sent_time':'999'},'pending':0,'mean_latency_s':.05,'temperature_c':55,'pids':{'readsb':1},'samples':{'samples_lost':0,'samples_dropped':0},'aligned_seconds':100}
class GuardTests(unittest.TestCase):
 def test_healthy(self):m.watch_check(snapshot(),None,now=1000)
 def test_stale_status(self):
  s=snapshot();s['updated_unix']=900
  with self.assertRaises(AssertionError):m.watch_check(s,None,now=1000)
 def test_stalled_rf(self):
  s=snapshot()
  with self.assertRaises(AssertionError):m.watch_check(s,s,now=1000)
 def test_loss(self):
  a=snapshot();b=copy.deepcopy(a);b['samples']['samples_lost']=1
  with self.assertRaises(AssertionError):m.watch_check(b,a,now=1000)
 def test_backlog_and_fr24(self):
  for key in ['pending','fr24']:
   s=snapshot()
   if key=='pending':s[key]=5
   else:s[key]['feed_status']='disconnected'
   with self.assertRaises(AssertionError):m.watch_check(s,None,now=1000)
 def test_three_failures_trigger_one_rollback(self):
  with tempfile.TemporaryDirectory() as tmp:
   state=Path(tmp)/'state.json';runtime=Path(tmp)/'guard.json';state.write_text(json.dumps({'state':'active','installed_sha256':{}}));s=snapshot();s['updated_unix']=900;calls=[]
   def rollback(reason):calls.append(reason);state.write_text(json.dumps({'state':'rolled_back'}))
   with patch.object(m,'STATE',state),patch.object(m,'RUNTIME',runtime),patch.object(m,'snapshot',return_value=s),patch.object(m,'rollback',side_effect=rollback),patch.object(m.time,'time',return_value=1000),patch.object(m.time,'sleep'):
    m.watch(15,3)
   self.assertEqual(len(calls),1);self.assertEqual(json.loads(runtime.read_text())['state'],'rolled_back')
 def test_exact_prior_library_restore(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);state=root/'state.json';backup=root/'backup';backup.mkdir();dest=root/'coherent.so';dest.write_bytes(b'new-rust');(backup/'file-0').write_bytes(b'old-C')
   record={'existed':True,'backup':'file-0','mode':0o640,'uid':os.getuid(),'gid':os.getgid(),'sha256':m.sha(backup/'file-0')};(backup/'files.json').write_text(json.dumps({str(dest):record}));state.write_text(json.dumps({'state':'active','backup':str(backup)}))
   with patch.object(m,'STATE',state),patch.object(m.subprocess,'run') as run:
    outcome=m.rollback('test fault');self.assertEqual(dest.read_bytes(),b'old-C');self.assertEqual(dest.stat().st_mode&0o777,0o640);self.assertEqual(outcome['state'],'rolled_back');run.assert_called_once_with(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
if __name__=='__main__':unittest.main(verbosity=2)

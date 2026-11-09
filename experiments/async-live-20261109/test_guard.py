import importlib.util,unittest,tempfile,json,hashlib
from pathlib import Path
from unittest.mock import patch
S=importlib.util.spec_from_file_location('profile_guard',Path(__file__).with_name('guard.py'));G=importlib.util.module_from_spec(S);S.loader.exec_module(G)
def sha(x):return hashlib.sha256(x).hexdigest()
class Tests(unittest.TestCase):
 def test_rollback_restores_profile_only(self):
  with tempfile.TemporaryDirectory() as raw:
   d=Path(raw);cfg=d/'config';cfg.write_bytes(b'new');drop=d/'dropin';drop.write_bytes(b'new');(d/'backup').write_bytes(b'old');calls=[]
   changes=[dict(path=str(cfg),before='backup',before_sha256=sha(b'old'),after_sha256=sha(b'new'),mode=0o600,uid=0,gid=0),dict(path=str(drop),before=None,before_sha256=None,after_sha256=sha(b'new'))]
   with patch.object(G,'D',d),patch.object(G,'call',lambda *a:calls.append(a)),patch.object(G.os,'chown'):
    G.restore(dict(changes=changes,prior_timers={'old.timer':True}),'test')
   self.assertEqual(cfg.read_bytes(),b'old');self.assertFalse(drop.exists());self.assertEqual(json.loads((d/'outcome.json').read_text())['result'],'restored_previous_pipeline')
   restarted=[c[2] for c in calls if c[:2]==('systemctl','restart')];self.assertEqual(restarted,['adsb-rescue-feed','adsb-rescue-shadow'])
 def test_external_change_is_preserved(self):
  with tempfile.TemporaryDirectory() as raw:
   d=Path(raw);p=d/'config';p.write_bytes(b'human');calls=[]
   with patch.object(G,'D',d),patch.object(G,'call',lambda *a:calls.append(a)):
    G.restore(dict(changes=[dict(path=str(p),before_sha256=sha(b'old'),after_sha256=sha(b'new'))]),'test')
   self.assertEqual(p.read_bytes(),b'human');self.assertFalse(any(c[:2]==('systemctl','restart') for c in calls))
if __name__=='__main__':unittest.main()

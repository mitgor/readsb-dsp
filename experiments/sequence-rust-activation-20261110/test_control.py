import unittest,tempfile,types,json,hashlib
from pathlib import Path
from unittest.mock import patch
H=Path(__file__).resolve().parent;s=(H/'control.py').read_text().replace("BASE=Path('/var/lib/adsb-rust-kernels-20261109')",'BASE=Path('+repr(str(H.parent/'rust-revalidate-20261109'))+')');m=types.ModuleType('sequence_test');exec(compile(s,str(H/'control.py'),'exec'),m.__dict__)
class Tests(unittest.TestCase):
 def test_exact_restore_remove_library_coordinator_only(self):
  with tempfile.TemporaryDirectory() as d:
   D=Path(d);loader=D/'loader.py';lib=D/'rust.so';loader.write_bytes(b'rust loader');lib.write_bytes(b'rust lib');(D/'old').write_bytes(b'C loader');sha=lambda b:hashlib.sha256(b).hexdigest();files=[dict(path=str(loader),before='old',before_sha256=sha(b'C loader'),after_sha256=sha(b'rust loader'),mode=0o644,uid=0,gid=0),dict(path=str(lib),before=None,before_sha256=None,after_sha256=sha(b'rust lib'),mode=0o755,uid=0,gid=0)];(D/'active.json').write_text(json.dumps(dict(state='active',files=files)));calls=[]
   with patch.object(m,'D',D),patch.object(m,'call',lambda *a:calls.append(a)),patch.object(m.os,'chown'):m.rollback('test')
   self.assertEqual(loader.read_bytes(),b'C loader');self.assertFalse(lib.exists());self.assertEqual([c for c in calls if c[:2]==('systemctl','restart')],[('systemctl','restart','adsb-rescue-shadow')]);self.assertEqual(json.loads((D/'active.json').read_text())['state'],'rolled_back')
 def test_human_change_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   D=Path(d);p=D/'loader.py';p.write_bytes(b'human');(D/'active.json').write_text(json.dumps(dict(state='active',files=[dict(path=str(p),before_sha256='c',after_sha256='r')])));calls=[]
   with patch.object(m,'D',D),patch.object(m,'call',lambda *a:calls.append(a)):m.rollback('test')
   self.assertEqual(p.read_bytes(),b'human');self.assertEqual(json.loads((D/'active.json').read_text())['state'],'superseded_by_external_change');self.assertFalse(any(c[:2]==('systemctl','restart') for c in calls))
if __name__=='__main__':unittest.main()

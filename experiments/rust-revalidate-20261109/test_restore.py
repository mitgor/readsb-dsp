import unittest,tempfile,json,hashlib,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent));import control
class Tests(unittest.TestCase):
 def test_exact_c_restore_only_restarts_coordinator(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);state=root/'state';state.mkdir();runtime=root/'runtime';runtime.mkdir();lib=root/'lib.so';lib.write_bytes(b'rust');(state/'old').write_bytes(b'c');loader=root/'loader.py';loader.write_bytes(b'new');(state/'old-loader').write_bytes(b'old');calls=[]
   h=lambda x:hashlib.sha256(x).hexdigest();files=[dict(path=str(lib),before='old',before_sha256=h(b'c'),after_sha256=h(b'rust'),mode=0o644,uid=0,gid=0),dict(path=str(loader),before='old-loader',before_sha256=h(b'old'),after_sha256=h(b'new'),mode=0o644,uid=0,gid=0)];(state/'active.json').write_text(json.dumps(dict(state='active',files=files,previous_guard_enabled=True)))
   with patch.object(control,'D',state),patch.object(control,'R',runtime),patch.object(control,'call',lambda *a:calls.append(a)),patch.object(control.os,'chown'):control.restore('test')
   self.assertEqual(lib.read_bytes(),b'c');self.assertEqual(loader.read_bytes(),b'old');self.assertEqual(json.loads((state/'active.json').read_text())['state'],'rolled_back');self.assertEqual([x for x in calls if x[:2]==('systemctl','restart')],[('systemctl','restart','adsb-rescue-shadow')])
 def test_external_file_is_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);lib=root/'lib';lib.write_bytes(b'human');(root/'active.json').write_text(json.dumps(dict(state='active',files=[dict(path=str(lib),after_sha256='rust',before_sha256='c')])));calls=[]
   with patch.object(control,'D',root),patch.object(control,'call',lambda *a:calls.append(a)):control.restore('test')
   self.assertEqual(lib.read_bytes(),b'human');self.assertEqual(json.loads((root/'active.json').read_text())['state'],'superseded_by_external_change');self.assertFalse(any(x[:2]==('systemctl','restart') for x in calls))
if __name__=='__main__':unittest.main()

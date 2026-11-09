import unittest,tempfile,types,hashlib,json
from pathlib import Path
from unittest.mock import patch
# Load the same base snapshot/policy code locally; no live operations on import.
here=Path(__file__).resolve().parent
source=(here/'control.py').read_text().replace("BASE=Path('/var/lib/adsb-rust-kernels-20261109')",'BASE=Path('+repr(str(here.parent/'rust-revalidate-20261109'))+')')
m=types.ModuleType('stream_control_test');exec(compile(source,str(here/'control.py'),'exec'),m.__dict__)
class Tests(unittest.TestCase):
 def test_rollback_exact_no_restart(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);b=d/'stream';b.write_bytes(b'rust');(d/'original').write_bytes(b'cpp');calls=[];s=dict(state='active',before_sha256=hashlib.sha256(b'cpp').hexdigest(),after_sha256=hashlib.sha256(b'rust').hexdigest(),mode=0o755,uid=0,gid=0);(d/'active.json').write_text(json.dumps(s))
   with patch.object(m,'D',d),patch.object(m,'B',b),patch.object(m.os,'chown'),patch.object(m.subprocess,'run',lambda *a,**k:calls.append(a)):m.rollback('test')
   self.assertEqual(b.read_bytes(),b'cpp');self.assertEqual(json.loads((d/'active.json').read_text())['state'],'rolled_back');self.assertFalse(any('restart' in a[0] for a in calls))
 def test_external_change_preserved(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);b=d/'stream';b.write_bytes(b'human');(d/'active.json').write_text(json.dumps(dict(state='active',before_sha256='c',after_sha256='r')))
   with patch.object(m,'D',d),patch.object(m,'B',b),patch.object(m.subprocess,'run'):m.rollback('test')
   self.assertEqual(b.read_bytes(),b'human');self.assertEqual(json.loads((d/'active.json').read_text())['state'],'superseded_by_external_change')
if __name__=='__main__':unittest.main()

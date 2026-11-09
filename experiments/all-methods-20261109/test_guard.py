import importlib.util,unittest,tempfile,hashlib
from unittest.mock import patch
from pathlib import Path
# Module setup creates only a test-owned directory.
with patch.object(Path,'mkdir'):
 spec=importlib.util.spec_from_file_location('guard',Path(__file__).with_name('guard.py'));g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class Budget(unittest.TestCase):
 def s(self,a,b=.2):return dict(max_recent_processing_s=a,stream1090=dict(last_wall_s=b),threads_alive=True)
 def test_healthy(self):self.assertIsNone(g.budget_reason(self.s(.6)))
 def test_total_margin(self):self.assertEqual(g.budget_reason(self.s(2.5)), 'processing_margin_exceeded')
 def test_not_only_worker(self):self.assertEqual(g.budget_reason(self.s(2.0,.8)), 'processing_margin_exceeded')
 def test_external_change_is_not_owned(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config';p.write_bytes(b'original');state={'configs':[{'path':str(p),'enabled_sha256':hashlib.sha256(b'original').hexdigest()}]}
   self.assertTrue(g.owned(state));p.write_bytes(b'human change');self.assertFalse(g.owned(state))
 def test_thread(self):self.assertEqual(g.budget_reason(dict(threads_alive=False)), 'worker_thread_unhealthy')
if __name__=='__main__':unittest.main()

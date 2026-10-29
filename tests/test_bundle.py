import tempfile,unittest,json
from pathlib import Path
import numpy as np
from deadsb.benchmark import benchmark
class BundleTests(unittest.TestCase):
 def test_offline_benchmark_full_and_stock_only(self):
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'noise.uc8';path.write_bytes(np.random.default_rng(12).integers(120,136,48000,dtype=np.uint8).tobytes())
   full=benchmark(root,path,Path(tmp)/'full.json',0);stock=benchmark(root,path,Path(tmp)/'stock.json',4)
   self.assertEqual(stock['candidate_count'],0);self.assertFalse(full['live_changes']);self.assertEqual(full['rf_seconds'],.01)
   self.assertNotIn('extras',full)
   with self.assertRaises(ValueError):benchmark(root,path,Path(tmp)/'full.json',0)

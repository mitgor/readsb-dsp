"""Fault injection: restore old file, remove newly installed files, no feeder restart."""
import json,runpy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
class Rollback(unittest.TestCase):
 def test_restore_existing_and_absent(self):
  m=runpy.run_path(str(ROOT/'tools/rust_coherent_mode.py'));g=m['restore'].__globals__
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);backup=d/'backup';backup.mkdir();existing=d/'existing';new=d/'new';existing.write_bytes(b'changed');new.write_bytes(b'added');stat=existing.stat();(backup/'old').write_bytes(b'original')
   records={str(existing):{'existed':True,'backup':'old','mode':0o644,'uid':stat.st_uid,'gid':stat.st_gid},str(new):{'existed':False}}
   (backup/'files.json').write_text(json.dumps(records))
   with patch.object(g['subprocess'],'run') as restart:g['restore'](backup)
   self.assertEqual(existing.read_bytes(),b'original');self.assertFalse(new.exists());self.assertEqual(restart.call_args.args[0],['systemctl','restart','adsb-rescue-shadow'])
 def test_health_failure(self):
  m=runpy.run_path(str(ROOT/'tools/rust_coherent_mode.py'))
  with self.assertRaises(AssertionError):m['watch_check']({'updated_unix':0,'feed_updated_unix':0},None,now=100)
if __name__=='__main__':unittest.main()

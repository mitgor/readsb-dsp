import unittest,tempfile,time,json,concurrent.futures
from pathlib import Path
from unittest.mock import patch
from rescue.async_live_engine import Engine
from rescue.method_metrics import MethodMetrics
from rescue.web_control import Controls
class Live:
 def snapshot(self):return [],dict(aircraft_unix=time.time())
class Tests(unittest.TestCase):
 def engine(self,d):
  m=MethodMetrics();e=Engine(Live(),Path(d)/'out',{'energy':True},None,metrics=m);e.hub.epoch=8
  f=concurrent.futures.Future();f.set_result(([],.125));e.jobs[(8,0)]=(f,time.monotonic());return e,m
 def test_completed_child_accounted_once_without_blocking(self):
  with tempfile.TemporaryDirectory() as d:
   e,m=self.engine(d)
   try:
    e.tick();e.last_tick=0;e.tick();self.assertEqual(m.cpu['stream1090'],.125);self.assertEqual(m.total_cpu,.125);self.assertEqual(e.report()['stream_child_cpu_s'],.125)
    r=m.report({'stream1090_extra':5,'energy_extra':5});self.assertEqual(r['methods']['stream1090']['cpu_ms_per_additional'],25.);self.assertEqual(r['methods']['stream1090']['cpu_share_percent'],100.)
   finally:e.close()
 def test_discarded_old_epoch_still_charged(self):
  with tempfile.TemporaryDirectory() as d:
   e,m=self.engine(d);e.hub.epoch=9
   try:e.tick();self.assertEqual(m.cpu['stream1090'],.125);self.assertEqual(e.count['old_stream_epoch'],1)
   finally:e.close()
 def test_noop_settings_preserve_exact_files_and_revision(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);(base/'adsb-rescue.json').write_text('{"energy":true,"sic":false}\n');(base/'adsb-rescue-workers.json').write_text('{"sequence_acquisition":true,"sequence_enabled":true,"acquisition_enabled":true}\n');(base/'adsb-far-capture.json').write_text('{"threshold_nm":180,"disk_limit_bytes":5000000000}\n');c=Controls(base=base,restart=lambda:self.fail('No restart for a no-op'),status=base/'missing');before=[p.read_bytes() for p in c.paths];s=c.read();result=c.apply(dict(revision=s['revision'],methods=s['methods'],capture={k:s['capture'][k] for k in ['packet_capture','continuous_capture']}));self.assertEqual(result['revision'],s['revision']);self.assertEqual(before,[p.read_bytes() for p in c.paths])
if __name__=='__main__':unittest.main()

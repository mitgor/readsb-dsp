import collections,json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from rescue.far_capture import Recorder
from rescue.far_training import FarTraining,valid_df17
from rescue.capture_schedule import CaptureSchedule
P='8d40621d58c382d690c8ac2863a7'
class FarTrainingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.r=Recorder(self.temp.name);self.r.cfg.update(continuous_capture=False);self.r.training=FarTraining(self.r);self.r.positions['40621d']=collections.deque([(99,190.,dict(available_unix=99.5,nic=8,nac_p=9,lat=53.,lon=15.,mlat_fields=[],tisb_fields=[]))]);self.raw=bytes(range(256))*80;self.r.iq(1,0,100,self.raw)
 def offer(self,tick=30000,unix=100.0025,source='stock',p=P):self.r.training.offer(dict(message_hex=p,signal_byte=30,wire_hex='aa'),tick,unix,1,source);self.r.drain()
 def records(self):return [json.loads(l) for l in b''.join(self.r.batch.parts['training.jsonl']).splitlines()]
 def test_independent_of_continuous_rf_quota_and_exact_sample_clock(self):
  self.r.schedule=CaptureSchedule(self.r.cfg['continuous_ram_bytes']);self.r.schedule.used=self.r.schedule.hour_seconds
  self.offer();rows=self.records();self.assertEqual(len(rows),1);r=rows[0];self.assertEqual(r['sample_start']%3,0);self.assertEqual(r['sample_count'],4800);self.assertEqual(r['iq_bytes'],9600);self.assertFalse(r['training_eligible']);self.assertEqual(r['event_ticks'],r['sample_start']*5+r['event_sample_4msps_in_window']*3);self.assertEqual(r['distance_nm'],190);self.assertEqual(self.r.batch.lengths['continuous.uc8'],0)
 def test_reject_predictions_bad_crc_bad_range_quality_future_and_mlat(self):
  self.offer(source='coherent');self.offer(p=P[:-1]+'0');self.assertFalse(self.records())
  for q in [dict(nic=0),dict(nac_p=0),dict(available_unix=101),dict(mlat_fields=['lat']),dict(tisb_fields=['lat'])]:
   old=self.r.positions['40621d'][0];v=dict(old[2],**q);self.r.positions['40621d']=collections.deque([(old[0],190.,v)]);self.offer();self.assertFalse(self.records());self.r.positions['40621d']=collections.deque([old])
  self.r.positions['40621d']=collections.deque([(99,179.,self.r.positions['40621d'][0][2])]);self.offer();self.assertFalse(self.records())
 def test_missing_rf_never_saves_wrong_epoch_or_gapped_window(self):
  self.r.ring.clear();self.offer();self.assertFalse(self.records());self.assertEqual(self.r.training.count['rf_gap_or_expired'],1)
 def test_one_aircraft_per_minute_and_restore(self):
  self.offer();self.offer(tick=31000);self.assertEqual(len(self.records()),1);status=self.r.training.report();other=FarTraining(self.r);other.restore(status);self.r.training=other;self.offer(tick=32000);self.assertEqual(len(self.records()),1)
 def test_disk_cap_no_early_flush_and_no_unbounded_training(self):
  self.r.cfg['disk_limit_bytes']=100;self.offer();self.assertFalse(self.records());self.assertGreater(self.r.training.count['shared_cap_skips'],0);self.assertFalse(self.r.flush())
 def test_bulk_archive_contains_checksums_and_raw_training_files(self):
  self.offer();self.assertTrue(self.r.flush(force=True));self.r.writer.join();import tarfile,hashlib
  with tarfile.open(next(Path(self.temp.name).glob('*.tar'))) as tar:
   m=json.load(tar.extractfile('manifest.json'));self.assertTrue(m['far_training']['enabled']);raw=tar.extractfile('training.uc8').read();r=json.loads(tar.extractfile('training.jsonl').read());self.assertEqual(hashlib.sha256(raw).hexdigest(),r['iq_sha256'])
 def test_crc(self):self.assertTrue(valid_df17(P));self.assertFalse(valid_df17(P[:-1]+'0'))
 def test_hourly_rf_spread(self):
  s=CaptureSchedule(128*1024**2);sample=0
  for h in range(12):
   unix=h*3600
   while s.permit(1,sample,unix,30000):s.recorded(1,sample,unix,30000);sample+=30000;unix+=.0125
   self.assertLessEqual(s.used,s.hour_seconds)
  self.assertEqual(s.bursts,12);self.assertLess(sample*2,128*1024**2)

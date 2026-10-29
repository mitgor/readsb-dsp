import collections,hashlib,json,tempfile,time,tarfile,unittest
from pathlib import Path
from unittest.mock import patch
from rescue.far_capture import Recorder,DEFAULTS,CORRECTION,address,wire
from rescue.wire import BeastParser
P='8d40621d58c382d690c8ac2863a7'
class CaptureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=Recorder(self.tmp.name);self.raw=bytes(range(256))*32;self.r.positions['40621d']=collections.deque([(99.,250.)]);self.r.far_present=True
 def frame(self,sample=1000):return dict(message_hex=P,ticks_12mhz=sample*5+CORRECTION,signal_byte=26,kind=51)
 def test_original_wire_fragmented_escape(self):
  b=wire(self.frame());p=BeastParser(preserve_wire=True);out=[]
  for c in b:out+=p.feed(bytes([c]))
  self.assertEqual(len(out),1);self.assertEqual(out[0]['wire_hex'],b.hex());self.assertNotIn('wire_hex',BeastParser().feed(b)[0])
 def test_packet_reference_matches_continuous_and_tar_checksums(self):
  self.r.iq(1,0,100,self.raw);self.r.frame(self.frame());self.assertEqual(self.r.batch.events,1);self.assertEqual(self.r.batch.lengths['packets.uc8'],0)
  row=json.loads(b''.join(self.r.batch.parts['packets.jsonl']));self.assertEqual(row['iq_byte_offset'],1616);self.assertEqual(row['iq_sha256'],hashlib.sha256(self.raw[1616:3152]).hexdigest());self.assertTrue(row['beast_original']);self.assertFalse(row['training_eligible'])
  self.assertTrue(self.r.flush(force=True));self.r.writer.join();self.assertIsNone(self.r.last_error)
  with tarfile.open(next(Path(self.tmp.name).glob('*.tar'))) as tar:
   m=json.load(tar.extractfile('manifest.json'));self.assertEqual(m['threshold_nm'],180);self.assertEqual(m['config']['threshold_nm'],180)
   for n,v in m['files'].items():self.assertEqual(hashlib.sha256(tar.extractfile(n).read()).hexdigest(),v['sha256'])
 def test_strict_threshold_and_prior_position(self):
  self.r.iq(1,0,100,self.raw)
  for positions in ([(99.,180.)],[(101.,260.)],[(80.,260.)]):
   self.r.positions['40621d']=collections.deque(positions);self.r.frame(self.frame())
  self.assertEqual(self.r.batch.events,0)
 def test_packet_between_new_and_old_threshold_is_saved(self):
  self.r.positions['40621d']=collections.deque([(99.,210.)]);self.r.iq(1,0,100,self.raw);self.r.frame(self.frame());self.assertEqual(self.r.batch.events,1)
 def test_external_context_never_supplies_packet_position(self):
  self.r.positions.clear();self.r.trigger_context=dict(active=[dict(icao='40621d',distance_nm=220,reason='external_local_missing')]);self.r.iq(1,0,100,self.raw);self.r.frame(self.frame());self.assertEqual(self.r.batch.events,0);self.assertGreater(self.r.batch.lengths['continuous.uc8'],0)
  rows=[json.loads(x) for x in b''.join(self.r.batch.parts['segments.jsonl']).splitlines()];self.assertFalse(rows[0]['training_eligible']);self.assertIn('capture_context',rows[0])
  self.r.iq(1,4096,100+4096/2400000,self.raw);rows=[json.loads(x) for x in b''.join(self.r.batch.parts['segments.jsonl']).splitlines()];self.assertNotIn('capture_context',rows[1]);self.assertEqual(rows[0]['capture_context_id'],rows[1]['capture_context_id'])
 def test_trigger_metadata_counted_in_ram_limit(self):
  self.r.trigger_context=dict(active=['x'*5000]);self.r.cfg['ram_limit_bytes']=len(self.raw)+1000;self.r.iq(1,0,100,self.raw);self.assertEqual(self.r.batch.bytes,0);self.assertEqual(self.r.count['ram_cap_skips'],1)
 def test_gap_detected_and_packet_snippet_missing(self):
  self.r.iq(1,0,100,self.raw[:1000]);self.r.iq(1,800,100+800/2400000,self.raw[:1000]);self.r.frame(self.frame(800));self.assertEqual(self.r.count['tap_gap_samples'],300);self.assertIsNone(self.r.extract(400,900))
 def test_continuous_budget_leaves_packet_reserve(self):
  self.r.cfg['continuous_ram_bytes']=100;self.r.iq(1,0,100,self.raw);self.r.frame(self.frame());self.assertEqual(self.r.batch.lengths['continuous.uc8'],0);self.assertEqual(self.r.batch.lengths['packets.uc8'],1536);self.assertEqual(self.r.count['continuous_ram_cap_skips'],1)
 def test_scheduled_packet_iq_references_only_retained_rf(self):
  from rescue.capture_schedule import CaptureSchedule
  self.r.schedule=CaptureSchedule(self.r.cfg['continuous_ram_bytes']);self.r.iq(1,0,100,self.raw);self.r.frame(self.frame())
  row=json.loads(b''.join(self.r.batch.parts['packets.jsonl']));self.assertTrue(row['raw_available']);self.assertEqual(row['iq_file'],'continuous.uc8')
  self.r.far_present=False;self.r.iq(1,4096,100+4096/2400000,self.raw);self.r.frame(self.frame(5000))
  rows=[json.loads(v) for v in b''.join(self.r.batch.parts['packets.jsonl']).splitlines()];self.assertFalse(rows[-1]['raw_available']);self.assertEqual(self.r.batch.lengths['packets.uc8'],0)
 def test_full_disk_preserves_old_and_no_early_flush(self):
  old=Path(self.tmp.name)/'old';old.write_bytes(b'keep');self.r.cfg['disk_limit_bytes']=100;self.r.iq(1,0,100,self.raw);self.r.frame(self.frame());self.assertEqual(self.r.batch.bytes,0);self.assertFalse(self.r.flush());self.assertEqual(old.read_bytes(),b'keep');self.assertGreater(self.r.count['disk_cap_skips'],0)
 def test_failed_save_preserved_then_retry_no_loss(self):
  self.r.iq(1,0,100,self.raw);self.r.frame(self.frame());batch=self.r.batch
  with patch('rescue.far_capture.tarfile.open',side_effect=OSError('test')):self.r.flush(True);self.r.writer.join()
  self.assertIs(self.r.failed_batch,batch);self.assertGreater(self.r.inflight,0);self.assertTrue(self.r.flush(True));self.r.writer.join();self.assertIsNone(self.r.failed_batch);self.assertEqual(self.r.count['saved_batches'],1);self.assertEqual(self.r.inflight,0)
 def test_epoch_and_off(self):
  self.r.cfg.update(packet_capture=False,continuous_capture=False);self.r.iq(1,0,100,self.raw);self.r.frame(self.frame());self.assertEqual(self.r.batch.bytes,0);self.r.iq(2,10000,200,self.raw);self.assertIsNone(self.r.extract(0,100))
 def test_address_parity_forms(self):
  self.assertEqual(address(P),'40621d');self.assertEqual(address('00000000000000'),'000000');self.assertIsNone(address('nothex'))
 def test_locked_buffers_release_after_save_and_ring_retirement(self):
  r=Recorder(self.tmp.name,lock_memory=True);r.far_present=True
  try:
   r.iq(1,0,100,self.raw);self.assertGreater(len(r.pins.pages)*r.pins.page,0);r.flush(True);r.writer.join();self.assertIsNone(r.last_error)
   for _,blob in r.ring:r.pins.unpin(blob)
   r.ring.clear();self.assertEqual(len(r.pins.pages),0)
  finally:
   for _,blob in r.ring:r.pins.unpin(blob)
 def test_lock_failure_never_retains_unlocked_rf(self):
  from unittest.mock import Mock
  self.r.pins=Mock();self.r.pins.pin.return_value=False
  with self.assertRaises(MemoryError):self.r.iq(1,0,100,self.raw)
  self.assertEqual(self.r.ring_bytes,0);self.assertEqual(self.r.batch.bytes,0)

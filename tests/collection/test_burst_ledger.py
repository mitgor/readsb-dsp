import json,tarfile,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from rescue.far_capture import Recorder,wire,CORRECTION
from rescue.burst_ledger import BurstLedger,TAIL_SECONDS
P='8d40621d58c382d690c8ac2863a7'
class LedgerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=Recorder(self.tmp.name);self.l=BurstLedger(self.r,network=False);self.r.ledger=self.l;self.addCleanup(self.l.close)
  self.clock=patch('rescue.burst_ledger.time.monotonic',return_value=100);self.clock.start();self.addCleanup(self.clock.stop)
  for s in ('stock','unified'):
   self.l.connection(s,True,now=60);self.l.ingest(s,wire(dict(ticks_12mhz=999999,message_hex=P,signal_byte=26,kind=51)),1,now=99)
 def rows(self):return [json.loads(x) for x in b''.join(self.r.batch.parts['ledger.jsonl']).splitlines()]
 def test_unknown_range_stock_and_actual_relay_bytes_preserved(self):
  self.assertTrue(self.l.ready());ident=self.l.begin_rf(1,1000,2000,100);self.l.end_rf()
  original=b'\x00opaque'+wire(dict(ticks_12mhz=200000,message_hex=P,signal_byte=26,kind=51))
  self.l.ingest('stock',original[:7],1,now=101);self.l.ingest('stock',original[7:],1,now=102)
  dsp=wire(dict(ticks_12mhz=201000,message_hex=P,signal_byte=0,kind=51));self.l.ingest('unified',dsp,1,now=103)
  self.l.annotation(dict(ticks=198602,message_hex=P,source='coherent'),1)
  with patch('rescue.burst_ledger.time.monotonic',return_value=109):
   for s in ('stock','unified'):self.l.ingest(s,wire(dict(ticks_12mhz=300000,message_hex=P,signal_byte=0,kind=51)),1,now=107.9)
   self.l.drain(force=True)
  self.assertIn(original,b''.join(self.r.batch.parts['stock-full.beast']));self.assertIn(dsp,b''.join(self.r.batch.parts['unified.beast']))
  end=[r for r in self.rows() if r['record']=='rf_burst_end'][0];self.assertEqual(end['burst_id'],ident);self.assertTrue(end['streams_complete']);self.assertTrue(any(r['record']=='dsp_annotation' for r in self.rows()))
 def test_disconnect_or_lag_marks_incomplete(self):
  self.l.begin_rf(1,1,10000000,100);self.l.end_rf();self.l.connection('unified',False,now=101)
  with patch('rescue.burst_ledger.time.monotonic',return_value=109):self.l.drain(force=True)
  self.assertFalse([r for r in self.rows() if r['record']=='rf_burst_end'][0]['streams_complete'])
 def test_warmup_and_epoch_reset_gate_rf(self):
  self.assertTrue(self.l.ready());self.l.set_epoch(2);self.assertFalse(self.l.ready());self.l.epoch_changed=60;self.assertTrue(self.l.ready())
  self.l.streams['unified']['since']=90;self.assertFalse(self.l.ready())
 def test_history_cap_is_bounded_and_pauses_capture(self):
  self.l.history_limit=1024;self.l.ingest('stock',b'x'*2048,1,now=100);self.assertLessEqual(self.l.history_bytes,1024);self.assertGreater(self.l.count['history_overflow'],0);self.assertFalse(self.l.ready())
 def test_postroll_blocks_save_and_batch_reserves_history(self):
  self.l.begin_rf(1,0,100,100);self.l.end_rf();self.assertFalse(self.r.flush(True))
  self.r.cfg['ram_limit_bytes']=self.l.history_limit+10;self.assertFalse(self.r.allowance(11))
 def test_overlapping_bursts_do_not_duplicate_stream_bytes(self):
  self.l.begin_rf(1,0,100,100);self.l.end_rf();n=self.r.batch.lengths['stock-full.beast'];self.l.begin_rf(1,1000,1100,101);self.l.end_rf();self.assertEqual(n,self.r.batch.lengths['stock-full.beast'])
 def test_rf_contiguous_burst_and_packet_window_ids(self):
  self.l.epoch=1;self.l.epoch_changed=60;self.r.far_present=True;raw=bytes([127,128])*4096
  self.r.iq(1,0,100,raw);self.r.iq(1,4096,100.0017,raw)
  rows=[json.loads(x) for x in b''.join(self.r.batch.parts['segments.jsonl']).splitlines()];self.assertEqual(rows[0]['burst_id'],rows[1]['burst_id']);self.assertEqual(self.l.active['sample_end'],8192)
  self.r.far_present=False;self.r.iq(1,8192,100.0034,raw);self.assertIsNone(self.l.active)
 def test_cap_never_deletes_existing_files(self):
  old=Path(self.tmp.name)/'keep';old.write_bytes(b'keep');self.r.cfg['disk_limit_bytes']=1;self.l.begin_rf(1,0,100,100);self.l.end_rf();self.assertEqual(self.r.batch.bytes,0);self.assertGreater(self.l.count['journal_cap_skips'],0);self.assertEqual(old.read_bytes(),b'keep')

 def test_saved_archive_has_exact_rf_and_structural_coverage(self):
  from rescue.ledger_verify import verify_ledger
  self.l.epoch=1;self.l.epoch_changed=60;self.r.far_present=True;raw=bytes([127,128])*4096
  self.r.iq(1,0,100,raw);self.r.far_present=False;self.r.iq(1,4096,100.0017,raw)
  with patch('rescue.burst_ledger.time.monotonic',return_value=109):
   for stream in ('stock','unified'):self.l.ingest(stream,wire(dict(ticks_12mhz=999999,message_hex=P,signal_byte=0,kind=51)),1,now=107.9)
   self.assertTrue(self.r.flush(True));self.r.writer.join();self.assertIsNone(self.r.last_error)
  with tarfile.open(next(Path(self.tmp.name).glob('*.tar'))) as tar:
   coverage=verify_ledger(tar);self.assertTrue(coverage['synchronized_coverage_complete']);self.assertEqual(coverage['rf_bytes'],len(raw));self.assertEqual(tar.extractfile('continuous.uc8').read(),raw)
  import subprocess,sys
  root=Path(__file__).resolve().parents[2];archive=next(Path(self.tmp.name).glob('*.tar'));export=Path(self.tmp.name)/'export'
  subprocess.run([sys.executable,str(root/'scripts/capture/verify.py'),str(archive)],check=True,capture_output=True)
  subprocess.run([sys.executable,str(root/'scripts/capture/export_bursts.py'),str(archive),'--output',str(export)],check=True,capture_output=True)
  self.assertEqual(next(export.glob('*.uc8')).read_bytes(),raw)

 def test_missing_end_or_misaligned_rf_is_rejected(self):
  import io
  from rescue.ledger_verify import verify_ledger
  class FakeTar:
   def extractfile(self,name):
    if name=='ledger.jsonl':return io.BytesIO(b'')
    if name=='segments.jsonl':return io.BytesIO(b'{"record":"continuous_segment","burst_id":"missing","epoch":1,"sample_start":0,"sample_count":1,"file":"continuous.uc8","byte_offset":0}\n')
    return io.BytesIO(b'')
   def getmember(self,name):
    class Member:size=0
    return Member()
  with self.assertRaisesRegex(ValueError,'no closed packet ledger'):verify_ledger(FakeTar())
 def test_scheduled_archive_preserves_exact_rf_and_closure(self):
  from rescue.capture_schedule import CaptureSchedule
  self.r.schedule=CaptureSchedule(self.r.cfg['continuous_ram_bytes'])
  self.test_saved_archive_has_exact_rf_and_structural_coverage()
 def test_connected_but_stalled_stream_does_not_claim_completeness(self):
  self.l.begin_rf(1,0,1000,100);self.l.end_rf()
  with patch('rescue.burst_ledger.time.monotonic',return_value=109):self.l.drain(force=True)
  self.assertFalse([r for r in self.rows() if r['record']=='rf_burst_end'][0]['streams_complete'])

 def test_epoch_change_invalidates_open_burst(self):
  self.l.epoch=1;self.l.begin_rf(1,0,1000,100);self.l.end_rf();self.l.set_epoch(2)
  with patch('rescue.burst_ledger.time.monotonic',return_value=109):self.l.drain(force=True)
  self.assertFalse([r for r in self.rows() if r['record']=='rf_burst_end'][0]['streams_complete']);self.assertEqual(self.l.count['clock_epoch_changes'],1)

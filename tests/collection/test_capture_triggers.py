import unittest
from rescue.capture_triggers import CaptureTriggers,external_tracks
class TriggerTests(unittest.TestCase):
 def local(self,t=100,d=220):return dict(icao='40621d',distance_nm=d,last_seen_unix=t,position_unix=t,source='local_stock')
 def ext(self,t=100):return dict(icao='abcdef',distance_nm=230,position_unix=t,reference_only=True)
 def test_local_holdover_expires_and_bursts_are_bounded(self):
  t=CaptureTriggers();self.assertEqual(t.update(100,[self.local()],[])[0]['reason'],'local_current')
  self.assertEqual(t.update(106,[],[])[0]['reason'],'local_holdover')
  self.assertTrue(t.update(107,[],[]));self.assertFalse(t.update(108,[],[]));self.assertFalse(t.update(130,[],[]));self.assertFalse(t.update(161,[],[]))
 def test_external_missing_trigger_cooldown_and_stale(self):
  t=CaptureTriggers();self.assertEqual(t.update(100,[],[self.ext()])[0]['reason'],'external_local_missing')
  self.assertFalse(t.update(103,[],[self.ext()]));self.assertFalse(t.update(160,[],[self.ext()]));self.assertTrue(t.update(161,[],[self.ext(161)]))
 def test_local_return_and_near_track_cancel_holdover(self):
  t=CaptureTriggers();t.update(100,[self.local()],[]);t.update(106,[],[])
  self.assertEqual(t.update(107,[self.local(107)],[])[0]['reason'],'local_current')
  t.update(108,[self.local(108,190)],[]);self.assertFalse(t.update(110,[],[]))
 def response(self):return dict(now=100,ac=[dict(hex='abcdef',lat=0,lon=3.6,seen_pos=1,seen=0,type='adsb_icao',alt_baro=35000)])
 def test_external_filters_and_provenance(self):
  rows=external_tracks(self.response(),(0,0),100,200);self.assertEqual(len(rows),1);self.assertFalse(rows[0]['training_eligible']);self.assertTrue(rows[0]['reference_only'])
  for patch in (dict(seen_pos=50),dict(lat=float('nan')),dict(mlat=['lat']),dict(alt_baro=1000),dict(hex='~abcde'),dict(type='tisb_icao')):
   d=self.response();d['ac'][0].update(patch);self.assertFalse(external_tracks(d,(0,0),100,200))
  with self.assertRaises(ValueError):external_tracks(self.response(),(0,0),200,200)
 def test_milliseconds_and_bad_timestamp(self):
  d=self.response();d['now']=1700000000000;self.assertEqual(len(external_tracks(d,(0,0),1700000000,200)),1)
  d['now']=float('nan')
  with self.assertRaises(ValueError):external_tracks(d,(0,0),100,200)

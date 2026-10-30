import unittest,numpy as np
from types import SimpleNamespace
from event_tap import EventTap
from rescue.runtime import RescueDecoder
class Tests(unittest.TestCase):
 def test_energy_published_before_later_stage_and_output_unchanged(self):
  d=SimpleNamespace(_event=RescueDecoder._event);seen={};events=[];rows=[];tap=EventTap(d,lambda r:rows.append(r));payload=np.frombuffer(bytes.fromhex('8d40621d58c382d690c8ac2863a7'),np.uint8)
  d._event(events,seen,10,payload,'energy',.8);self.assertEqual(len(rows),1);self.assertFalse(rows[0]['admitted']);self.assertEqual(rows[0]['source'],'energy')
  expected=[];RescueDecoder._event(expected,{},10,payload,'energy',.8);self.assertEqual(events,expected)
  d._event(events,seen,10,payload,'energy',.8);self.assertEqual(len(rows),1);tap.close();self.assertIs(d._event,RescueDecoder._event)
 def test_callback_failure_does_not_damage_decoder(self):
  def fail(_):raise RuntimeError('test queue unavailable')
  d=SimpleNamespace(_event=RescueDecoder._event);tap=EventTap(d,fail);events=[];d._event(events,None,10,np.zeros(14,np.uint8),'matched',.8);self.assertEqual(len(events),1);self.assertEqual(tap.count['callback_failed'],1);tap.close()
if __name__=='__main__':unittest.main()

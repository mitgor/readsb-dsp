import copy,unittest
from extended_trial import check_progress
class Tests(unittest.TestCase):
 def test_quiet_rf_does_not_require_alignment_or_aircraft(self):
  a={'stock':dict(samples_processed=100,messages=0),'relay':{'counts':dict(stock_bytes_relayed=0)}};b=copy.deepcopy(a);b['stock']['samples_processed']=200;check_progress(a,b,10,11)
 def test_active_aircraft_require_relay_progress(self):
  a={'stock':dict(samples_processed=100,messages=1),'relay':{'counts':dict(stock_bytes_relayed=10)}};b=copy.deepcopy(a);b['stock'].update(samples_processed=200,messages=2)
  with self.assertRaises(AssertionError):check_progress(a,b,10,11)
 def test_real_dsp_stall_still_fails_closed(self):
  a={'stock':dict(samples_processed=100,messages=0),'relay':{'counts':dict(stock_bytes_relayed=0)}};b=copy.deepcopy(a);b['stock']['samples_processed']=200
  with self.assertRaises(AssertionError):check_progress(a,b,10,10)
if __name__=='__main__':unittest.main()

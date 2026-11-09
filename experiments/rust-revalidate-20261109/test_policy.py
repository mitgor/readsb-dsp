import unittest
from policy import assess
class Tests(unittest.TestCase):
 def healthy(self):return dict(started_unix=0,updated_unix=100,feed_updated_unix=100,threads_alive=True,completed=40,iq_packets=500,aligned=20,pending=0,processing_s=.5,receiver_pid=1,samples={'samples_lost':0,'samples_dropped':0},stock_connected=True,fr24_routed=True,asynchronous=True,holdback_s=0,fr24_connected=True,capture_error=None,capture_cap=5000000000,temperature_c=55,protected_pids={'readsb':1,'fr24':2},late_stock_duplicates=0,cache_evictions=0,outbox_overflow=0)
 def test_alignment_idle_is_not_compute_stall(self):
  s=self.healthy();previous=assess(s,None,100)
  for now in [115,130,145,160]:s.update(completed=s['completed']+40,iq_packets=s['iq_packets']+500,updated_unix=now,feed_updated_unix=now);previous=assess(s,previous,now)
  self.assertFalse(previous['reasons']);self.assertIn('alignment_not_advancing',previous['notes'])
 def test_real_worker_stall_with_live_iq(self):
  s=self.healthy();previous=assess(s,None,100)
  for now in [115,130,145,160]:s.update(iq_packets=s['iq_packets']+500,updated_unix=now,feed_updated_unix=now);previous=assess(s,previous,now)
  self.assertIn('worker_completion_stall',previous['reasons'])
 def test_input_stall_classified_separately(self):
  s=self.healthy();previous=assess(s,None,100);s.update(updated_unix=160,feed_updated_unix=160);now=assess(s,previous,160);self.assertIn('upstream_iq_input_stall',now['reasons'])
 def test_new_worker_process_gets_grace(self):
  s=self.healthy();old=assess(s,None,100);s.update(started_unix=160,completed=0,iq_packets=0,aligned=0,updated_unix=161,feed_updated_unix=161);n=assess(s,old,161);self.assertTrue(n['startup_grace']);self.assertFalse(n['reasons'])
 def test_budget_loss_and_collector_faults(self):
  s=self.healthy();old=assess(s,None,100);s.update(updated_unix=110,feed_updated_unix=110,completed=80,iq_packets=1000,processing_s=2.8,capture_cap=1000,samples={'samples_lost':1,'samples_dropped':0});n=assess(s,old,110)
  for x in ['stock_sample_loss_increased','capture_unhealthy','three_second_budget_margin']:self.assertIn(x,n['reasons'])
if __name__=='__main__':unittest.main()

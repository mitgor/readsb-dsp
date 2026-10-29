import json,tempfile,unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace as NS
from deadsb.governor import Config,Governor,read_cpu
from deadsb.policy import reduced

class GovernorTests(unittest.TestCase):
 def setUp(self):self.t=0.;self.g=Governor(clock=lambda:self.t)
 def feed(self,busy,seconds=1,**kw):
  for _ in range(seconds):
   self.t+=1
   if not hasattr(self,'total'):self.total=self.idle=0
   self.total+=400;self.idle+=round(400*(1-busy/100));self.g.observe(self.total,self.idle,now=self.t,**kw)
 def test_counter_math_and_guest_not_counted_twice(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'stat';p.write_text('cpu 100 2 20 200 10 3 4 1 90 1\n');self.assertEqual(read_cpu(p),(340,210))
 def test_overload_sheds_and_slowly_recovers(self):
  self.feed(70,20);self.assertEqual(self.g.level,4)
  self.feed(10,100);self.assertEqual(self.g.level,3)
  self.feed(10,190);self.assertEqual(self.g.level,0)
 def test_backlog_temperature_and_stale_are_fail_closed(self):
  self.feed(10,4,backlog=True);self.assertEqual(self.g.policy()['level'],4)
  self.g.level=0;self.feed(10,1,temperature=76);self.assertEqual(self.g.level,4)
  self.g.level=0;self.t+=6;self.assertEqual(self.g.policy()['level'],4)
 def test_unknown_nonfinite_bad_bounds_rejected(self):
  for d in [{'target_percent':True},{'target_percent':float('nan')},{'ceiling_percent':50},{'unknown':2},{'recovery_seconds':1}]:
   with self.assertRaises(ValueError):Config.from_dict(d)
 def test_disabled_is_explicit_full(self):
  self.g.config=Config(enabled=False);self.assertEqual(self.g.policy()['level'],0)
 def test_counter_reset_disables_optional_work(self):
  self.feed(10,4);self.t+=1;self.g.observe(1,1,now=self.t);self.assertEqual(self.g.level,4)
 def test_policy_never_enables_and_restores_on_exception(self):
  d=NS(neural_enabled=False,budget=64,classical=NS(stages=('timing','soft')),pulse_model=None,broad_crc=True)
  with self.assertRaises(RuntimeError):
   with reduced(d,'dsp',{'level':3}) as skip:
    self.assertFalse(skip);self.assertFalse(d.neural_enabled);self.assertIsNone(d.classical);raise RuntimeError()
  self.assertFalse(d.neural_enabled);self.assertEqual(d.budget,64);self.assertEqual(d.classical.stages,('timing','soft'));self.assertTrue(d.broad_crc)
 def test_full_is_noop_and_stock_only_skips_both_roles(self):
  for role in ['dsp','coherent']:
   with reduced(NS(),'dsp',{'level':0}) as skip:self.assertFalse(skip)
   d=NS(decoder=NS(budget=48),budget=64)
   with reduced(d,role,{'level':4}) as skip:self.assertTrue(skip)
 def test_coherent_reduced_never_enables_disabled_branches(self):
  d=NS(decoder=NS(budget=48,pair_retry=False,sequence_enabled=False,acquisition_enabled=False))
  with reduced(d,'coherent',{'level':1}):self.assertEqual(d.decoder.budget,24);self.assertFalse(d.decoder.pair_retry)
  self.assertEqual(d.decoder.budget,48)
if __name__=='__main__':unittest.main()

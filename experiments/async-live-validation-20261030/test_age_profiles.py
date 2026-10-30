import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'async-relay-20261030'))
from async_relay import AsyncFanIn
from dedup import HistoryMerge
from prototype import ImmediateRelay
from rescue.feed import beast,CORRECTION
from rescue.wire import BeastParser
class Test(unittest.TestCase):
 def test_diagnostic_age_is_explicit_and_default_stays_strict(self):
  p='8d40621d58c382d690c8ac2863a7'
  for limit,expected in [(.25,False),(3,True)]:
   r=ImmediateRelay(HistoryMerge,max_extra_age=limit)
   for t in [10000,24000000]:
    wire=beast(p,t);r.stock(wire,BeastParser().feed(wire)[0],1,epoch=7);r.ready(1)
   # Same legitimate payload, different RF transmission time, prior stock exists.
   r.batch(dict(epoch=7,created_unix=2,alignment={'verified':True},extra=[dict(source='energy',ticks=12000000-CORRECTION,message_hex=p)]),1,2,{'energy':True});self.assertEqual(bool(r.ready(1)),expected)
if __name__=='__main__':unittest.main()

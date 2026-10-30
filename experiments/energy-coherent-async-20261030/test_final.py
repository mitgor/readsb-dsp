import sys,unittest
from bench import Final
from rescue.feed import CORRECTION
class TestFinal(unittest.TestCase):
 def test_shared_cache_repetitions_stock_priority_and_policy(self):
  f=Final(sys.argv[1]);p='8d40621d58c382d690c8ac2863a7';epoch=7
  def stock(t):return dict(ticks=t,ticks_12mhz=t+CORRECTION,signal_byte=26,message_hex=p)
  def extra(t,source='energy'):return dict(source=source,epoch=epoch,ticks=t,message_hex=p,alignment=dict(verified=True,matches=20,median_abs_error_us=0))
  try:
   f.stock(stock(10000),epoch,1);f.emit(extra(20000),1.001);f.emit(extra(20000,'coherent'),1.002);self.assertEqual(len(f.extra),1)
   f.emit(extra(40000),1.003);self.assertEqual(len(f.extra),2)
   f.stock(stock(20000),epoch,1.004);self.assertEqual(f.stock_records,2);self.assertEqual(f.cache.count['late_stock_after_extra_race'],1)
   r=extra(80000);r['message_hex']=p[:-1]+'0'
   with self.assertRaises(ValueError):f.emit(r,1.005)
   self.assertEqual(f.stock_sha.digest(),f.stock_expected.digest())
  finally:f.cache.close()
if __name__=='__main__':unittest.main(argv=[sys.argv[0]])

import unittest
from bench_stream import clock,offsets,unique_offsets
class Tests(unittest.TestCase):
 def test_overlapping_anchor_counts_once(self):self.assertIsNone(clock(unique_offsets([(0,[(12,'a',1)]*10)])))
 def test_minimum_never_lowered(self):self.assertIsNone(clock([0]*9));self.assertEqual(clock([12]*10),12)
 def test_unstable_offset_rejected(self):self.assertIsNone(clock([0]*5+[1000]*5))
 def test_only_same_payload_local_clock_matches(self):self.assertEqual(offsets([(100,'a'),(200,'b')],[dict(ticks=112,message_hex='a')]),[12])
if __name__=='__main__':unittest.main()

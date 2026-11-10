import unittest
from rescue.dashboard_status import compact_status
class CompactStatusTests(unittest.TestCase):
 def test_counters_preserved_without_research_records(self):
  source={'distance':{'total':{'energy_extra':17}},'counts':{'aligned_seconds':12},'crc_research_recent':[{'raw':'private'}]*512,'models':['private'],'updated_unix':42}
  result=compact_status(source)
  self.assertEqual(result,{'distance':source['distance'],'counts':source['counts'],'updated_unix':42})
  self.assertIn('crc_research_recent',source)

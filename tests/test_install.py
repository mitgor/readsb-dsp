import importlib.util, math, tempfile, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('installer',Path(__file__).resolve().parents[1]/'tools/install.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class InstallTests(unittest.TestCase):
 def test_units_have_one_sdr_owner_and_separate_outputs(self):
  units=m.units(52,13,38.6)
  self.assertEqual(len(units),4)
  self.assertEqual(sum('--device-type rtlsdr' in v for v in units.values()),1)
  self.assertIn('ADSB_RESCUE_SOCKET=/run/readsb-dsp/iq.sock',units['readsb-dsp-receiver.service'])
  self.assertIn('--readsb-json /run/readsb-dsp',units['readsb-dsp-decoder.service'])
  self.assertIn('rescue.async_shadow',units['readsb-dsp-decoder.service'])
  self.assertIn('rescue.async_feed',units['readsb-dsp-relay.service'])
  self.assertIn('--worker-config /etc/readsb-dsp/workers.json',units['readsb-dsp-relay.service'])
  self.assertIn('--no-logging',units['readsb-dsp-decoder.service'])
  self.assertIn('--port 31005',units['readsb-dsp-relay.service'])
  self.assertTrue(all('RuntimeDirectoryPreserve=yes' in s for s in units.values()))
 def test_invalid_coordinates_and_gain_rejected(self):
  for args in [(91,0,30),(0,181,30),(0,0,float('nan')),(0,0,-1)]:
   with self.assertRaises(ValueError):m.units(*args)

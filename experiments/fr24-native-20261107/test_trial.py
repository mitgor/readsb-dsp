import importlib.util,json,tempfile,unittest,os,time
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('native_trial',Path(__file__).with_name('trial.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_gain_and_position_options_preserved(self):
  text='RECEIVER_OPTIONS="--device 0 --device-type rtlsdr --gain 38.6 --ppm 0"\nDECODER_OPTIONS="--lat 52 --lon 13 --max-range 450"\n'
  with patch.object(Path,'read_text',return_value=text):o=m.options()
  self.assertEqual(o,dict(gain=38.6,ppm=0.,device='0',lat=52.,lon=13.,max_range=450.))
 def test_only_decoder_launch_fields_changed_key_and_mlat_preserved(self):
  original='receiver="beast-tcp"\nhost="127.0.0.1:31005"\nfr24key="dummy"\nmlat="no"\nraw="no"\n'
  result=m.config(original,'--gain 38.6 --ppm 0')
  for line in ['host="127.0.0.1:31005"','fr24key="dummy"','mlat="no"','procargs="--gain 38.6 --ppm 0"','receiver="dvbt"']:self.assertIn(line,result)
  self.assertNotIn('receiver="beast-tcp"',result)
 def test_unknown_runtime_directory_is_not_removed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'active').touch();(p/'bridge').mkdir()
   with patch.multiple(m,MARKER=p/'active',BRIDGE=p/'bridge',TARGET=p/'target'):
    with self.assertRaises(RuntimeError):m.runtime()
   self.assertTrue((p/'bridge').is_dir())
 def test_stale_decoder_error_does_not_abort_new_launch(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'stderr';p.write_text('Unknown option --old');os.utime(p,(100,100));self.assertIsNone(m.decoder_error(p,200))
   p.write_text('Unknown option --new');self.assertIn('Unknown',m.decoder_error(p,200))
   p.write_text('Found tuner\nGain reported by device: 38.60 dB');self.assertIsNone(m.decoder_error(p,200))
 def test_restore_releases_native_before_starting_readsb_and_thaws_buffers(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'state.json').write_text(json.dumps(dict(closed=False,files=[],active_before={'readsb.service':True,'fr24feed.service':True,**{u:True for u in m.PAUSED},'adsb-rescue-feed-guard.timer':True,'adsb-unified-graphs.timer':True})));(p/'active').touch();(p/'bridge').symlink_to(p/'target');calls=[];frozen=set(m.PAUSED)
   def run(*args):
    calls.append(args)
    if args[:2]==('systemctl','thaw'):frozen.discard(args[2])
    return ''
   with patch.multiple(m,D=p,S=p/'state.json',MARKER=p/'active',BRIDGE=p/'bridge',TARGET=p/'target',run=run,active=lambda u:True,prop=lambda u,k:'frozen' if u in frozen else 'running',monitor=lambda:dict(feed_status='connected',rx_connected='1'),snapshot=lambda:dict(restored=True)):
    m.restore('test')
   self.assertLess(calls.index(('systemctl','stop','fr24feed')),calls.index(('systemctl','start','readsb.service')))
   self.assertLess(calls.index(('systemctl','start','readsb.service')),calls.index(('systemctl','thaw',m.PAUSED[0])))
   self.assertTrue(json.loads((p/'state.json').read_text())['closed']);self.assertFalse((p/'bridge').is_symlink());self.assertFalse((p/'active').exists())
 def test_safety_files_remain_if_original_receiver_fails_to_reconnect(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);safety=p/(m.SAFETY+'.service');safety.write_text('owned test safety')
   state=dict(closed=False,files=[dict(path=str(safety),exists=False)],active_before={'readsb.service':True,'fr24feed.service':True,**{u:True for u in m.PAUSED},'adsb-rescue-feed-guard.timer':True,'adsb-unified-graphs.timer':True});(p/'state.json').write_text(json.dumps(state));(p/'active').touch();(p/'bridge').symlink_to(p/'target');calls=[]
   with patch.multiple(m,D=p,S=p/'state.json',MARKER=p/'active',BRIDGE=p/'bridge',TARGET=p/'target',run=lambda *a:calls.append(a) or '',active=lambda u:True,prop=lambda u,k:'running',monitor=lambda:dict(feed_status='disconnected',rx_connected='0')),patch.object(m.time,'sleep',return_value=None):
    with self.assertRaises(RuntimeError):m.restore('test failure')
   self.assertTrue(safety.exists());self.assertFalse(any(a[:2]==('systemctl','disable') for a in calls));self.assertFalse(json.loads((p/'state.json').read_text())['closed'])
if __name__=='__main__':unittest.main()

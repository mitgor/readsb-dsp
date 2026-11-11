"""Exercise both manual selection branches without touching receiver services."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

def main():
 spec=importlib.util.spec_from_file_location('selector',Path(__file__).with_name('select.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);mode={'holdback_s':0,'enabled':True,'state':'active','relay_pid':10};calls=[]
 def snapshot():return dict(pids={'readsb':1,'fr24feed':2,'adsb-rescue-feed':mode['relay_pid']})
 def healthy(a,b):assert a['pids']==b['pids']
 def read(p):
  if str(p).endswith('lowlatency.json'):return {'enabled':True}
  if p=='state':return {'state':mode['state']}
  return {'enabled':mode['enabled']}
 def command(args,**kwargs):
  calls.append(args);mode.update(holdback_s=3 if args[1]=='rollback' else 0,enabled=args[1]!='rollback',state='rolled_back' if args[1]=='rollback' else 'active',relay_pid=mode['relay_pid']+1)
 fake=dict(G=dict(snapshot=snapshot,healthy=healthy,capture=lambda:None),ready=lambda:dict(holdback_s=mode['holdback_s']),read=read,STATE='state',CFG='cfg')
 with patch('runpy.run_path',return_value=fake),patch('subprocess.run',side_effect=command):
  m.select('arrival_order');assert not calls
  m.select('ordered_3s');assert mode['holdback_s']==3 and calls[-1][1]=='rollback'
  m.select('arrival_order');assert mode['holdback_s']==0 and calls[-1][1]=='activate' and '/var/lib/adsb-arrival-relay/release' in calls[-1]
  mode['state']='rollback_conflict'
  try:m.select('ordered_3s');raise AssertionError('conflict ignored')
  except RuntimeError:pass
 print('Manual selection/no-op, both modes, native preservation and conflict controls passed')
if __name__=='__main__':main()

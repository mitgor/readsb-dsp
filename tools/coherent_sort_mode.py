#!/usr/bin/env python3
"""Atomic coherent-sort deployment with preserved stock feed and rollback.

Run on the receiver as root. Only the rescue shadow service is restarted.
"""
import argparse,ctypes,hashlib,json,os,shutil,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path('/home/pi/adsb-neural-rescue');STATE=Path('/var/lib/adsb-rescue/coherent-sort-active.json')
PROTECTED=('readsb','fr24feed','adsb-rescue-feed','adsbexchange-feed','adsb-far-capture')
CONFIGS=('/etc/default/adsb-rescue-workers.json','/etc/default/adsb-rescue.json','/etc/default/readsb','/etc/fr24feed.ini')
FILES={'src/rescue/_coherent.so':'experiments/coherent-sort/.work/base-typed.so','src/rescue/_coherent_pair.so':'experiments/coherent-sort/.work/pair-typed.so','src/rescue/coherent_kernel.c':'src/rescue/coherent_kernel.c','src/rescue/coherent_sort.h':'src/rescue/coherent_sort.h'}
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pid(n):return int(subprocess.check_output(['systemctl','show',n,'-p','MainPID','--value'],text=True).strip())
def snapshot():
 s=read('/run/adsb-rescue/status.json');f=read('/run/adsb-rescue/feed-status.json');stats=read('/run/readsb/stats.json')
 with urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=5) as r:fr=json.load(r)
 crc=s.get('crc_verification',{}).get('archive',{})
 return {'unix':time.time(),'pids':{n:pid(n) for n in PROTECTED},'shadow_pid':pid('adsb-rescue-shadow'),'started_unix':s['started_unix'],'updated_unix':s['updated_unix'],'feed_updated_unix':f['updated_unix'],'threads_alive':s['threads_alive'],'gain_db':s['health']['gain_db'],'methods':s['method_switches'],'worker_config':s['workers']['config'],'worker_roles':s['workers']['role_by_pid'],'workers':s['workers']['affinity_by_pid'],'pending':s['workers']['pending_jobs'],'mean_latency_s':s['workers']['mean_batch_latency_s'],'aligned_seconds':s['counts'].get('aligned_seconds',0),'shed':s['workers']['incomplete_rf_seconds_shed'],'samples':{k:stats['total']['local'][k] for k in ('samples_lost','samples_dropped')},'feed':{'stock_connected':f['stock_connected'],'fr24_routed':f['fr24_routed'],'counts':{k:f['counts'].get(k,0) for k in ('stock_bytes_relayed','dsp_frames_relayed','relayed_coherent')},'upstream_error':f.get('upstream_error')},'fr24':{k:fr.get(k) for k in ('feed_status','rx_connected','feed_last_ac_sent_time','feed_num_ac_tracked')},'crc_archive':{'disk_bytes':sum(x['bytes'] for x in crc.get('files',[])),'ram_bytes':crc.get('compressed_ram_bytes',0),'error':crc.get('error'),'saved_files':len(crc.get('files',[]))},'config_sha256':{p:sha(p) for p in CONFIGS},'temperature_c':int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000}
def healthy(old,s):
 now=time.time()
 assert all(s['pids'].values()) and s['pids']==old['pids'],'Protected service PID changed'
 assert s['config_sha256']==old['config_sha256'],'Configuration changed'
 assert s['samples']==old['samples'],'Sample loss/drop counter changed'
 assert s['gain_db']==old['gain_db'] and s['methods']==old['methods'] and s['worker_config']==old['worker_config'],'Decoder selection changed'
 assert now-s['updated_unix']<15 and now-s['feed_updated_unix']<6,'Stale status'
 assert s['threads_alive'] and s['feed']['stock_connected'] and s['feed']['fr24_routed'],'Relay path unhealthy'
 assert s['fr24']['feed_status']=='connected' and str(s['fr24']['rx_connected'])=='1','FR24 disconnected'
 assert now-int(s['fr24']['feed_last_ac_sent_time'] or 0)<90,'FR24 uploads stale'
 assert s['mean_latency_s']<.75 and s['pending']<=4 and s['temperature_c']<75,'Worker health bound exceeded'
 assert not s['crc_archive']['error'],'Archive error'
def atomic(dest,data,record):
 temp=dest.with_name(dest.name+'.sort-new');temp.write_bytes(data);os.chmod(temp,record['mode']);os.chown(temp,record['uid'],record['gid']);os.replace(temp,dest)
def restore(backup):
 for dest,record in read(backup/'files.json').items():
  p=Path(dest)
  if record['existed']:atomic(p,(backup/record['backup']).read_bytes(),record)
  else:p.unlink(missing_ok=True)
 subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
def mapped(s):
 result={}
 for worker,role in s['worker_roles'].items():
  if role!='coherent':continue
  maps=Path('/proc')/worker/'maps';lines=maps.read_text().splitlines();found=[]
  for name in ('_coherent.so','_coherent_pair.so'):
   path=ROOT/'src/rescue'/name;ino=path.stat().st_ino
   assert any(len(parts:=line.split())>=6 and parts[4]==str(ino) and parts[-1]==str(path) for line in lines),f'{worker} does not map installed {name}'
   found.append(name)
  result[worker]=found
 assert len(result)==2,'Expected two coherent workers'
 return result

def activate(stage,observe):
 assert not STATE.exists(),'Coherent sort already active; inspect status before another deployment'
 proof=read(stage/'pi.json');assert proof['windows']>=3000
 for mode in ('base','pair'):
  assert proof['results'][mode]['exact_output_parity'] and proof['results'][mode]['saving_percent']>5
  assert proof['installed_parity'][mode]['exact_all_arrays']
  installed=ROOT/'src/rescue'/('_coherent.so' if mode=='base' else '_coherent_pair.so')
  assert sha(installed)==proof['installed_parity'][mode]['sha256'],'Installed baseline changed after validation'
 before=snapshot();healthy(before,before)
 assert before['crc_archive']['disk_bytes']+before['crc_archive']['ram_bytes']+8*1024**2<512*1024**2,'Insufficient archive room for graceful close'
 backup=Path('/var/backups')/('adsb-coherent-sort-'+str(time.time_ns()));backup.mkdir(mode=0o700)
 records={};hashes={}
 for index,(dest,source) in enumerate(FILES.items()):
  p=ROOT/dest;stat=p.stat() if p.exists() else p.parent.stat();record={'existed':p.exists(),'backup':f'file-{index}','mode':stat.st_mode&0o777 if p.exists() else 0o644,'uid':stat.st_uid,'gid':stat.st_gid}
  if p.exists():shutil.copy2(p,backup/record['backup']);record['sha256']=sha(p)
  records[str(p)]=record;hashes[dest]=sha(stage/source)
 (backup/'files.json').write_text(json.dumps(records,indent=2)+'\n')
 report={'before':before,'backup':str(backup),'installed_sha256':hashes,'proof_sha256':sha(stage/'pi.json'),'samples':[],'activated':False}
 (backup/'deployment.json').write_text(json.dumps(report,indent=2)+'\n')
 try:
  for dest,source in FILES.items():atomic(ROOT/dest,(stage/source).read_bytes(),records[str(ROOT/dest)]);assert sha(ROOT/dest)==hashes[dest]
  for name in ('_coherent.so','_coherent_pair.so'):assert ctypes.CDLL(str(ROOT/'src/rescue'/name)).rescue_coherent_init()==0
  switched=time.time();subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
  for _ in range(45):
   s=snapshot()
   if s['started_unix']>switched and s['aligned_seconds']>=5:break
   time.sleep(2)
  else:raise RuntimeError('New workers did not become ready')
  started=s['aligned_seconds'];since=time.time();first=s
  while True:
   healthy(before,s);report['samples'].append(s);report['mapped_libraries']=mapped(s)
   (backup/'deployment.json').write_text(json.dumps(report,indent=2)+'\n')
   if time.time()-since>=observe:break
   time.sleep(10);s=snapshot()
  assert s['aligned_seconds']-started>=observe*.8,'Aligned processing too slow'
  assert s['shed']-first['shed']<=max(5,observe*.05),'RF shedding exceeded bound'
  for k in ('stock_bytes_relayed','dsp_frames_relayed','relayed_coherent'):assert s['feed']['counts'][k]>before['feed']['counts'][k],k+' did not progress'
  for dest in FILES:assert sha(ROOT/dest)==hashes[dest]
  report['activated']=True;(backup/'deployment.json').write_text(json.dumps(report,indent=2)+'\n')
  STATE.write_text(json.dumps({'state':'active','backup':str(backup),'installed_sha256':hashes},indent=2)+'\n')
  print(json.dumps({'activated':True,'backup':str(backup),'observation_s':observe,'aligned_seconds':s['aligned_seconds']-started,'coherent_frames_relayed':s['feed']['counts']['relayed_coherent']-before['feed']['counts']['relayed_coherent'],'protected_pids_unchanged':True},indent=2))
 except BaseException as error:
  report['error']=repr(error);restore(backup);report['rolled_back']=True;(backup/'deployment.json').write_text(json.dumps(report,indent=2)+'\n');raise

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=('activate','rollback','status'));p.add_argument('--stage',type=Path);p.add_argument('--observe',type=int,default=90);a=p.parse_args()
 if a.action=='status':print(json.dumps(read(STATE) if STATE.exists() else {'state':'inactive'},indent=2));return
 assert os.geteuid()==0,'Run as root'
 if a.action=='activate':assert a.stage and a.observe>=60;activate(a.stage,a.observe)
 else:
  state=read(STATE);restore(Path(state['backup']));STATE.unlink();print('Prior coherent libraries restored; shadow service restarted')
if __name__=='__main__':main()

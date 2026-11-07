#!/usr/bin/env python3
"""Finite official FR24 DVB-T test with frozen training RAM and file rollback."""
import argparse,datetime,fcntl,hashlib,json,math,os,re,shlex,shutil,subprocess,time,urllib.request
from pathlib import Path
D=Path('/var/lib/adsb-fr24-native-20261107');S=D/'state.json';MARKER=D/'active'
PAUSED=['adsb-rescue-shadow.service','adsb-far-capture.service']
CONDITIONED=PAUSED+['readsb.service','adsb-rescue-feed-guard.service','adsb-rescue-feed-fallback.service']
HEALTH='adsb-fr24-native-health-20261107';RESTORE='adsb-fr24-native-restore-20261107';SAFETY='adsb-fr24-native-safety-20261107'
CONFIG=Path('/etc/fr24feed.ini');BRIDGE=Path('/run/readsb');TARGET=Path('/run/dump1090-mutability')
def run(*cmd):return subprocess.check_output(cmd,stderr=subprocess.STDOUT,text=True)
def active(u):return subprocess.run(['systemctl','is-active','--quiet',u]).returncode==0
def prop(u,k):return run('systemctl','show',u,'-p',k,'--value').strip()
def save(path,value):
 path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.chmod(0o600);os.replace(tmp,path)
 with path.open('rb') as f:os.fsync(f.fileno())
 fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def monitor():
 m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=5));return {k:m.get(k) for k in ['num_messages','feed_status','rx_connected','feed_num_ac_tracked','feed_num_ac_adsb_tracked','timing_is_valid','feed_last_ac_sent_time','feed_current_mode']}
def snapshot():
 out=dict(unix=time.time(),pids={u:prop(u,'MainPID') for u in ['readsb','fr24feed','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture','adsbexchange-feed','adsbexchange-mlat']},freezers={u:prop(u,'FreezerState') for u in PAUSED})
 try:out['fr24']=monitor()
 except Exception as e:out['fr24_error']=str(e)
 return out
def backup(path,state):
 p=Path(path);assert not p.is_symlink(),'Unexpected symlink in managed configuration'
 row=dict(path=str(p),exists=p.exists())
 if p.exists():
  st=p.stat();name=D/'backup'/str(len(state['files']));shutil.copy2(p,name);row.update(backup=str(name),sha256=sha(name),mode=st.st_mode&0o777,uid=st.st_uid,gid=st.st_gid)
 state['files'].append(row);save(S,state)
def put(path,text,state):
 p=Path(path);backup(p,state);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.native-tmp');tmp.write_text(text)
 row=state['files'][-1];tmp.chmod(row.get('mode',0o644));os.chown(tmp,row.get('uid',0),row.get('gid',0));os.replace(tmp,p)
def options():
 data={}
 for line in Path('/etc/default/readsb').read_text().splitlines():
  if '=' in line:
   key,v=line.split('=',1);parts=shlex.split(v);data[key]=shlex.split(parts[0]) if len(parts)==1 else parts
 def get(name,key,default=None):
  row=data[name];return row[row.index(key)+1] if key in row else default
 assert get('RECEIVER_OPTIONS','--device-type')=='rtlsdr'
 return dict(gain=float(get('RECEIVER_OPTIONS','--gain')),ppm=float(get('RECEIVER_OPTIONS','--ppm','0')),device=get('RECEIVER_OPTIONS','--device'),lat=float(get('DECODER_OPTIONS','--lat')),lon=float(get('DECODER_OPTIONS','--lon')),max_range=float(get('DECODER_OPTIONS','--max-range','450')))
def config(original,args):
 # Keep key/MLAT and all unrelated fields. Replace only input and decoder launch.
 d=dict(receiver='dvbt',path='/usr/lib/fr24/dump1090',procargs=args,bs='no',raw='no');lines=[]
 for line in original.splitlines():
  key=line.split('=',1)[0].strip() if '=' in line else None
  if key in d:continue
  lines.append(line)
 return '\n'.join(lines)+'\n'+''.join(k+'="'+v+'"\n' for k,v in d.items())
def runtime():
 assert MARKER.exists(),'No active native trial'
 if BRIDGE.is_symlink():assert BRIDGE.readlink()==TARGET
 elif BRIDGE.exists():raise RuntimeError('Unexpected live /run/readsb directory; refusing overwrite')
 else:BRIDGE.symlink_to(TARGET)
def dump_processes():
 out=[]
 for p in Path('/proc').glob('[0-9]*/cmdline'):
  try:
   argv=p.read_bytes().split(b'\0');name=Path(argv[0].decode()).name;group=(p.parent/'cgroup').read_text()
   if name in ('dump1090','dump1090-mutability') and '/fr24feed.service' in group:out.append(dict(pid=int(p.parent.name),argv=[x.decode() for x in argv if x]))
  except (OSError,UnicodeError):pass
 return out
def gain_lines(since):
 lines=run('journalctl','-u','fr24feed','--since','@'+str(int(since)),'--no-pager','-o','cat').splitlines()
 p=Path('/dev/shm/decoder.txt')
 if p.exists():lines+=p.read_text(errors='replace').splitlines()
 return [x for x in lines if re.search(r'gain',x,re.I) and len(x)<250]
def restore(reason):
 state=json.loads(S.read_text())
 if state.get('closed'):return
 run('systemctl','stop',HEALTH+'.timer')
 run('systemctl','disable',HEALTH+'.timer',RESTORE+'.timer',SAFETY+'.timer')
 state['restore_started_unix']=time.time();state['restore_reason']=reason;save(S,state)
 run('systemctl','stop','fr24feed')
 if BRIDGE.is_symlink():
  assert BRIDGE.readlink()==TARGET;BRIDGE.unlink()
 elif BRIDGE.exists() and MARKER.exists():raise RuntimeError('Runtime bridge changed externally')
 for row in reversed(state['files']):
  p=Path(row['path'])
  if row['exists']:
   assert sha(row['backup'])==row['sha256'];shutil.copy2(row['backup'],p);p.chmod(row['mode']);os.chown(p,row['uid'],row['gid'])
  else:p.unlink(missing_ok=True)
 MARKER.unlink(missing_ok=True);run('systemctl','daemon-reload')
 if state['active_before']['readsb.service']:run('systemctl','start','readsb.service')
 for u in PAUSED:
  if prop(u,'FreezerState')=='frozen':run('systemctl','thaw',u)
  if state['active_before'][u] and not active(u):run('systemctl','start',u)
 if state['active_before']['fr24feed.service']:run('systemctl','start','fr24feed.service')
 for u in ['adsb-rescue-feed-guard.timer','adsb-unified-graphs.timer']:
  if state['active_before'][u]:run('systemctl','start',u)
 for u in [RESTORE+'.timer',SAFETY+'.timer']:run('systemctl','stop',u)
 for _ in range(90):
  try:
   m=monitor()
   if m['feed_status']=='connected' and str(m['rx_connected'])=='1':break
  except Exception:pass
  time.sleep(1)
 else:raise RuntimeError('Original FR24 did not reconnect; inspect saved state')
 assert active('readsb') and all(prop(u,'FreezerState')=='running' for u in PAUSED)
 state.update(closed=True,closed_unix=time.time(),result='restored_original_setup',after_restore=snapshot());save(S,state);save(D/'restoration.json',state['after_restore'])
def health():
 state=json.loads(S.read_text())
 if state.get('closed'):return
 if time.time()>=state['deadline_unix']:restore('48_hour_deadline');return
 try:
  assert MARKER.exists() and sha(CONFIG)==state['test_config_sha256'],'FR24 test configuration changed'
  assert not active('readsb'),'readsb unexpectedly active'
  assert all(prop(u,'FreezerState')=='frozen' for u in PAUSED),'Training capture/decoder unexpectedly thawed'
  assert active('fr24feed') and len(dump_processes())==1,'Native decoder unavailable'
  argv=dump_processes()[0]['argv'];assert argv[max(i for i,v in enumerate(argv) if v=='--gain')+1]==str(state['options']['gain']) and '--enable-agc' not in argv,'Gain changed'
  assert time.time()-(TARGET/'aircraft.json').stat().st_mtime<15,'Native JSON stale'
  m=monitor();assert m['feed_status']=='connected' and str(m['rx_connected'])=='1','FR24 link/receiver disconnected'
  row=dict(unix=time.time(),fr24=m,decoder_pid=dump_processes()[0]['pid'],mode='official_dvbt',gain_db=state['options']['gain']);status=Path('/run/adsb-fr24-native-20261107');status.mkdir(exist_ok=True);save(status/'status.json',{**row,'deadline_unix':state['deadline_unix']})
  # RAM samples each minute; SD summary only once per UTC hour.
  with (status/'samples.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
  hour=int(time.time()//3600)
  if state.get('last_saved_hour')!=hour:
   with (D/'hourly.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
   state['last_saved_hour']=hour;save(S,state)
 except BaseException as e:
  state['health_failure']=repr(e);save(S,state);restore('native_health_failure:'+repr(e));raise

def activate():
 assert not S.exists() and not MARKER.exists(),'Existing trial must not be overwritten'
 assert active('readsb') and active('fr24feed') and all(prop(u,'FreezerState')=='running' for u in PAUSED)
 assert not active('adsb-coherent-rust-guard') and not active('adsb-rust-methods-guard')
 opt=options();assert opt['gain']==38.6 and opt['device'].isdigit();assert Path('/usr/lib/fr24/dump1090').resolve()==Path('/usr/bin/dump1090-mutability')
 capture=json.loads(Path('/run/adsb-far-capture/status.json').read_text());assert not capture['saving'] and not capture['error'] and capture['disk_limit_bytes']==5000000000
 (D/'backup').mkdir(mode=0o700,parents=True);D.chmod(0o700)
 units=['readsb.service','fr24feed.service',*PAUSED,'adsb-rescue-feed-guard.timer','adsb-unified-graphs.timer']
 state=dict(started_unix=time.time(),before=snapshot(),options=opt,files=[],closed=False,active_before={u:active(u) for u in units},capture_before=capture)
 save(S,state)
 original=CONFIG.read_text();assert re.search(r'^receiver="beast-tcp"$',original,re.M)
 flags=['--device-index',opt['device'],'--gain',str(opt['gain']),'--ppm',str(opt['ppm']),'--net','--net-bind-address','127.0.0.1','--net-ri-port','0','--net-bi-port','0','--net-ro-port','30002','--net-sbs-port','30003','--net-bo-port','30005','--lat',str(opt['lat']),'--lon',str(opt['lon']),'--max-range',str(opt['max_range']),'--write-json',str(TARGET),'--write-json-every','1','--json-location-accuracy','2']
 test=config(original,' '.join(flags));tmp=D/'candidate.ini';tmp.write_text(test);tmp.chmod(0o600)
 v=subprocess.run(['/usr/bin/fr24feed','--validate-config','--config-file='+str(tmp)],capture_output=True,text=True,timeout=20);(D/'config-validation.private.log').write_text(v.stdout+v.stderr);assert v.returncode==0
 try:
  # Calendar guards are installed BEFORE touching receiver ownership.
  state['measurement_start_unix']=math.ceil((time.time()+600)/3600)*3600;state['deadline_unix']=state['measurement_start_unix']+172800;save(S,state)
  for name,offset in [(RESTORE,0),(SAFETY,600)]:
   command=datetime.datetime.fromtimestamp(state['deadline_unix']+offset,datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
   put('/etc/systemd/system/'+name+'.service','[Unit]\nDescription=Restore original ADS-B receiver after native FR24 test\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'trial.py')+' --restore\n',state)
   put('/etc/systemd/system/'+name+'.timer','[Unit]\nDescription=Finite native FR24 test restoration\n[Timer]\nOnCalendar='+command+'\nPersistent=yes\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n',state)
  put('/etc/systemd/system/'+HEALTH+'.service','[Unit]\nDescription=Native FR24 test health monitor\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'trial.py')+' --health\nNice=19\n',state)
  put('/etc/systemd/system/'+HEALTH+'.timer','[Timer]\nOnActiveSec=60\nOnUnitActiveSec=60\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n',state)
  run('systemctl','daemon-reload');run('systemctl','enable','--now',RESTORE+'.timer',SAFETY+'.timer')
  for u in CONDITIONED:
   p='/etc/systemd/system/'+u+'.d/99-stock-fr24-native-test.conf';assert not Path(p).exists();put(p,'[Unit]\nConditionPathExists=!'+str(MARKER)+'\n',state)
  p='/etc/systemd/system/fr24feed.service.d/99-stock-fr24-native-test.conf';assert not Path(p).exists();put(p,'[Service]\nExecStartPre=/usr/bin/python3 '+str(D/'trial.py')+' --prepare-runtime\n',state)
  run('systemctl','stop','adsb-rescue-feed-guard.timer','adsb-unified-graphs.timer');run('systemctl','stop','adsb-rescue-feed-guard.service')
  MARKER.write_text('native_fr24_test\n');run('systemctl','daemon-reload')
  for u in PAUSED:run('systemctl','freeze',u)
  assert all(prop(u,'FreezerState')=='frozen' for u in PAUSED)
  run('systemctl','stop','fr24feed');run('systemctl','stop','readsb');assert not active('readsb')
  runtime();put(CONFIG,test,state);state['test_config_sha256']=sha(CONFIG);save(S,state)
  run('systemctl','start','fr24feed')
  for _ in range(120):
   try:
    if monitor()['feed_status']=='connected' and str(monitor()['rx_connected'])=='1' and len(dump_processes())==1 and (TARGET/'stats.json').exists():break
   except Exception:pass
   time.sleep(1)
  else:raise RuntimeError('Native FR24 startup did not become healthy')
  time.sleep(3);lines=gain_lines(state['started_unix']);save(D/'gain-verification.json',lines)
  assert any(re.search(r'gain.*38[.,]6',line,re.I) for line in lines),'Hardware tuner gain log did not confirm38.6dB'
  state['measurement_start_unix']=math.ceil((time.time()+120)/3600)*3600
  old_deadline=state['deadline_unix'];state['deadline_unix']=state['measurement_start_unix']+172800
  for name,offset in [(RESTORE,0),(SAFETY,600)]:
   p=Path('/etc/systemd/system')/(name+'.timer');text=p.read_text();assert 'Description=Finite native FR24 test restoration' in text
   date=datetime.datetime.fromtimestamp(state['deadline_unix']+offset,datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
   text,n=re.subn(r'^OnCalendar=.*$', 'OnCalendar='+date,text,flags=re.M);assert n==1;p.write_text(text)
  save(S,state);run('systemctl','daemon-reload');run('systemctl','restart',RESTORE+'.timer',SAFETY+'.timer')
  state['activated_unix']=time.time();state['after']=snapshot();state['native_decoder']=dump_processes();save(S,state)
  health();run('systemctl','enable','--now',HEALTH+'.timer');save(D/'activation.json',dict(success=True,measurement_start_unix=state['measurement_start_unix'],deadline_unix=state['deadline_unix'],gain_db=opt['gain'],native_decoder_pid=dump_processes()[0]['pid']))
  print(json.dumps(json.loads((D/'activation.json').read_text())))
 except BaseException as e:
  state=json.loads(S.read_text());state['activation_error']=repr(e);save(S,state);restore('activation_failure:'+repr(e));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--activate',action='store_true');p.add_argument('--restore',action='store_true');p.add_argument('--health',action='store_true');p.add_argument('--prepare-runtime',action='store_true');a=p.parse_args()
 if a.prepare_runtime:runtime()
 else:
  lock=open('/run/lock/adsb-fr24-native-20261107.lock','w');fcntl.flock(lock,fcntl.LOCK_EX)
  if a.activate:activate()
  elif a.restore:restore('automatic_or_requested_restoration')
  elif a.health:health()
  else:p.error('Choose an action')

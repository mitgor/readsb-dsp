"""Install additive asynchronous profile; own rollback before touching live services."""
import argparse,base64,json,subprocess,hashlib,tarfile,io
from pathlib import Path
H=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);a=p.parse_args();manifest=json.loads((a.build/'manifest.json').read_text())
files={p.name:base64.b64encode(p.read_bytes()).decode() for p in a.build.glob('*.py')};guard=(H/'guard.py').read_bytes()
code=r'''
import pathlib,json,hashlib,subprocess,time,os,urllib.request,base64
P=pathlib.Path;D=P('/var/lib/adsb-async-live-20261109');ROOT=P('/home/pi/adsb-neural-rescue');assert not D.exists(),'Inspect previous activation rather than overwrite'
def sha(b):return hashlib.sha256(b).hexdigest()
def call(*a):return subprocess.run(a,check=True,timeout=100,stdout=subprocess.DEVNULL)
def atomic(p,b,mode=0o644,uid=0,gid=0):
 t=p.with_suffix('.async-tmp');t.write_bytes(b);t.chmod(mode);os.chown(t,uid,gid);os.replace(t,p)
s=json.loads(P('/run/adsb-rescue/status.json').read_text());f=json.loads(P('/run/adsb-rescue/feed-status.json').read_text());c=json.loads(P('/run/adsb-far-capture/status.json').read_text());m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=3))
assert f['stock_connected'] and f['fr24_routed'] and f['holdback_s']==3 and m['feed_status']=='connected' and str(m['rx_connected'])=='1'
assert c['disk_limit_bytes']==5000000000 and not c.get('error') and time.time()-s['updated_unix']<20
assert s['method_switches']['sic'] and s['workers']['transport']=='bounded_shared_ring'
assert sha((ROOT/'src/rescue/shadow.py').read_bytes())==MANIFEST['base_shadow_sha256']
for sub,key in [('',s['archive']),('/crc-verification',s['crc_verification']['archive'])]:
 archive=P('/var/lib/adsb-rescue'+sub);used=sum(x.stat().st_size for x in archive.glob('batch-*.jsonl.gz'));assert not key.get('error') and used+key['compressed_ram_bytes']+8*1048576<512*1048576,'No save headroom'
for name,b64 in FILES.items():
 p=ROOT/'src/rescue'/name;raw=base64.b64decode(b64);assert sha(raw)==MANIFEST['files'][name];assert not p.exists() or p.read_bytes()==raw
 # New modules are inert until both service drop-ins are activated.
 atomic(p,raw)
D.mkdir(mode=0o700);(D/'guard.py').write_bytes(base64.b64decode(GUARD));(D/'guard.py').chmod(0o700)
changes=[]
def change(path,after):
 p=P(path);assert not p.is_symlink();before=p.read_bytes() if p.exists() else None;st=p.stat() if p.exists() else None;n=str(len(changes))+'.before'
 if before is not None:(D/n).write_bytes(before)
 changes.append(dict(path=str(p),before=n if before is not None else None,before_sha256=sha(before) if before else None,after_sha256=sha(after),mode=(st.st_mode&0o777) if st else 0o644,uid=st.st_uid if st else 0,gid=st.st_gid if st else 0));(D/(str(len(changes)-1)+'.after')).write_bytes(after)
cfg=P('/etc/default/adsb-rescue.json');methods=json.loads(cfg.read_text());methods['sic']=False;change(str(cfg),(json.dumps(methods,indent=2)+'\n').encode())
for unit,module in [('adsb-rescue-shadow','async_live_shadow'),('adsb-rescue-feed','async_live_feed')]:
 p=P('/etc/systemd/system/'+unit+'.service.d/99-asynchronous.conf');assert not p.exists();p.parent.mkdir(exist_ok=True)
 if unit=='adsb-rescue-shadow':
  raw=subprocess.check_output(['systemctl','show',unit,'-p','ExecStart','--value'],text=True);command=raw.split('argv[]=')[1].split(' ;')[0].strip();assert ' -m rescue.shadow ' in command;command=command.replace(' -m rescue.shadow ',' -m rescue.async_live_shadow ')
 else:command='/home/pi/adsb-neural-rescue/.venv/bin/python -m rescue.async_live_feed'
 change(str(p),('[Service]\nExecStart=\nExecStart='+command+'\n').encode())
protected={u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in ['readsb','fr24feed','adsb-far-capture','adsbexchange-feed']}
prior={u:subprocess.run(['systemctl','is-active','--quiet',u]).returncode==0 for u in ['adsb-all-methods-budget-20261109-v2.timer','adsb-rescue-feed-guard.timer']}
state=dict(activated_unix=time.time(),boot_id=P('/proc/sys/kernel/random/boot_id').read_text().strip(),changes=changes,protected_pids=protected,prior_timers=prior,gain=s['health']['gain_db'],stock_loss={k:s['health']['local'].get(k,0) for k in ['samples_lost','samples_dropped']},methods={**s['method_switches'],'sic':False},manifest=MANIFEST)
for name,j in [('activation.json',state),('before-worker.private.json',s),('before-feed.json',f),('before-collector.private.json',c)]:
 p=D/name;p.write_text(json.dumps(j,indent=2)+'\n')
 with p.open('rb') as h:os.fsync(h.fileno())
unit=P('/etc/systemd/system/adsb-async-live-20261109.service');timer=unit.with_suffix('.timer');assert not unit.exists() and not timer.exists()
unit.write_text('[Unit]\nDescription=Guard asynchronous DSP relay and roll back unhealthy activation\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'guard.py')+'\nTimeoutStartSec=240\nNice=19\n')
timer.write_text('[Unit]\nDescription=Monitor asynchronous DSP profile\n[Timer]\nOnBootSec=90\nOnActiveSec=10\nOnUnitInactiveSec=10\nAccuracySec=1\n[Install]\nWantedBy=timers.target\n')
call('systemctl','daemon-reload');call('systemctl','enable','--now',timer.name)
for u in prior:call('systemctl','stop',u)
# The new profile guard replaces the old method-only guard until rollback.
call('systemctl','disable','adsb-all-methods-budget-20261109-v2.timer')
try:
 for i,r in enumerate(changes):
  p=P(r['path']);assert (sha(p.read_bytes()) if p.exists() else None)==r['before_sha256'];atomic(p,(D/(str(i)+'.after')).read_bytes(),r['mode'],r['uid'],r['gid'])
 call('systemctl','daemon-reload')
 # Relay starts immediately forwarding stock while DSP saves its own CRC RAM and restarts.
 call('systemctl','restart','adsb-rescue-feed')
 for _ in range(60):
  try:
   f=json.loads(P('/run/adsb-rescue/feed-status.json').read_text())
   if f.get('asynchronous') and f['started_unix']>=state['activated_unix'] and f['stock_connected'] and f.get('current_connection_stock_bytes_relayed',0)>0:break
  except (OSError,ValueError):pass
  time.sleep(.5)
 else:raise RuntimeError('New relay not ready')
 call('systemctl','restart','adsb-rescue-shadow')
 call('systemctl','start','adsb-rescue-feed-guard.timer')
except BaseException:
 import sys;sys.path.insert(0,str(D));import guard;guard.restore(state,'activation_failed');raise
print(json.dumps(dict(activation='started',protected_pids=protected,rollback_timer=timer.name)))
'''
script='FILES='+repr(files)+'\nMANIFEST='+repr(manifest)+'\nGUARD='+repr(base64.b64encode(guard).decode())+'\n'+code
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=script,text=True,timeout=200))

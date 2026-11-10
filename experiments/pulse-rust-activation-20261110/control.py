"""Pulse-only guarded activation; coordinate DSP restarts with existing guard."""
from pathlib import Path
import argparse,json,hashlib,os,sys,time,subprocess,fcntl,ctypes,importlib.util
BASE=Path('/var/lib/adsb-rust-kernels-20261109');sys.path.insert(0,str(BASE));spec=importlib.util.spec_from_file_location('base_rust_control',BASE/'control.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
D=Path('/var/lib/adsb-pulse-rust-20261110');R=Path('/run/adsb-pulse-rust-20261110');ROOT=Path('/home/pi/adsb-neural-rescue/src/rescue');T='adsb-pulse-rust-20261110.timer'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else None
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2)+'\n');os.replace(tmp,p)
 if str(p).startswith('/var/'):
  with p.open('rb') as f:os.fsync(f.fileno())
  fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def call(*args):subprocess.run(args,check=True,timeout=120,stdout=subprocess.DEVNULL)
def atomic(p,raw,m):
 tmp=p.with_suffix('.seq-new');tmp.write_bytes(raw);tmp.chmod(m['mode']);os.chown(tmp,m['uid'],m['gid'])
 with tmp.open('rb') as f:os.fsync(f.fileno())
 os.replace(tmp,p);fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def owns(s,before=False):return all(sha(r['path']) in ([r['after_sha256'],r['before_sha256']] if before else [r['after_sha256']]) for r in s['files'])
def snapshot():
 x=base.snapshot();s=read('/run/adsb-rescue/status.json');f=read('/run/adsb-rescue/feed-status.json');st=s['stream1090'];x.update(stream_rf=st['counts'].get('processed_rf_seconds',0),stream_error=st.get('last_error'),pulse_windows=s.get('counts',{}).get('pulse_windows',0),pulse_relay=f['counts'].get('relayed_pulse',0),stream_sha256=sha(st['binary']));return x

def mapped(s):
 out={};lib=ROOT/'_pulse_discriminant.so';inode=str(lib.stat().st_ino)
 for pid,role in s['worker_roles'].items():
  if role!='dsp':continue
  lines=Path('/proc/'+pid+'/maps').read_text().splitlines();assert any(len(z:=l.split())>=6 and z[4]==inode and z[5]==str(lib) for l in lines),'Rust pulse not mapped in DSP worker '+pid;out[pid]=str(lib)
 assert len(out)==2,'Expected both DSP workers';base.mapped(s)
 seq=ROOT/'_sequence_rust.so';seq_inode=str(seq.stat().st_ino);seen=0
 for pid,role in s['worker_roles'].items():
  if role!='coherent':continue
  lines=Path('/proc/'+pid+'/maps').read_text().splitlines();assert any(len(z:=l.split())>=6 and z[4]==seq_inode and z[5]==str(seq) for l in lines),'Existing Rust sequence mapping lost';seen+=1
 assert seen==2

 return out

def marker():
 lib=ctypes.CDLL(str(ROOT/'_pulse_discriminant.so'));f=lib.rescue_pulse_backend;f.restype=ctypes.c_char_p;value=f().decode();assert value=='rust-1.99.1/pulse-discriminant';return value

def rollback(reason):
 s=read(D/'active.json')
 if s['state'] not in ['active','activating','restoring','rollback_failed']:return
 if not owns(s,True):s.update(state='superseded_by_external_change',reason=reason);save(D/'active.json',s);call('systemctl','disable','--now',T);return
 s.update(state='restoring',reason=reason);save(D/'active.json',s)
 try:
  for r in s['files']:
   p=Path(r['path'])
   if r['before'] is None:p.unlink(missing_ok=True)
   else:
    raw=(D/r['before']).read_bytes();assert hashlib.sha256(raw).hexdigest()==r['before_sha256'];atomic(p,raw,r)
  call('systemctl','restart','adsb-rescue-shadow');s.update(state='rolled_back',rolled_back_unix=time.time());save(D/'active.json',s);call('systemctl','disable','--now',T)
 except BaseException as e:s.update(state='rollback_failed',error=repr(e));save(D/'active.json',s);raise

def check():
 state=read(D/'active.json')
 if state['state'] in ['restoring','rollback_failed']:rollback('retry_incomplete_restore');return
 if state['state'] not in ['active','activating']:return
 if not owns(state):rollback('pulse_files_changed');return
 previous=read(R/'guard.json') if (R/'guard.json').exists() else {};x=snapshot();g=base.assess(x,previous,time.time())
 if x['stream_error']:g['reasons'].append('Stream_error: '+str(x['stream_error']))
 if not g['startup_grace']:
  try:g['mapped']=mapped(x);g['backend']=marker()
  except Exception as e:g['reasons'].append(str(e))
 n=previous.get('consecutive_failures',0)+1 if g['reasons'] else 0;g.update(unix=time.time(),state='degraded' if n else 'healthy',consecutive_failures=n);save(R/'guard.json',g)
 if n:
  save(D/('failure-'+str(time.time_ns())+'.json'),dict(previous=previous,current=g))
  if n>=3:rollback(';'.join(g['reasons']))
 return g

def activate(observe):
 s=read(D/'active.json');assert s['state']=='prepared' and owns(s,True);assert all(sha(r['path'])==r['before_sha256'] for r in s['files']);before=snapshot();assert before['fr24_connected'] and not base.assess(before,None,time.time())['reasons'];status=read('/run/adsb-rescue/status.json')
 for sub,a in [('',status['archive']),('/crc-verification',status['crc_verification']['archive'])]:
  saved=sum(p.stat().st_size for p in Path('/var/lib/adsb-rescue'+sub).glob('batch-*.jsonl.gz'));assert not a.get('error') and saved+a['compressed_ram_bytes']+8*1048576<512*1048576,'Insufficient normal shutdown cache-save headroom'
 s.update(state='activating',activated_unix=time.time(),before=before);save(D/'active.json',s);call('systemctl','enable','--now',T)
 try:
  for r in s['files']:
   raw=(D/r['candidate']).read_bytes();assert hashlib.sha256(raw).hexdigest()==r['after_sha256'];atomic(Path(r['path']),raw,r)
  backend=marker();restart=time.time();call('systemctl','restart','adsb-rescue-shadow')
  for _ in range(100):
   try:
    x=snapshot()
    if x['started_unix']>=restart and x['completed']>20:break
   except (OSError,ValueError,KeyError):pass
   time.sleep(1)
  else:raise RuntimeError('Rust pulse startup timed out')
  first=x;began=time.monotonic();samples=[]
  while True:
   g=check();assert g and not g['reasons'],g;x=g['snapshot'];assert x['protected_pids']==before['protected_pids'],'Receiver/feeder/collector PID changed';assert x['config_hashes']==before['config_hashes'] and x['methods']==before['methods'] and x['worker_config']==before['worker_config'] and x['gain']==before['gain'] and x['samples']==before['samples'] and x['stream_sha256']==before['stream_sha256'];g['mapped']=mapped(x);samples.append(g);save(R/'observation.json',dict(samples=samples))
   if time.monotonic()-began>=observe:break
   time.sleep(5)
  assert x['completed']>first['completed']+4*observe and x['aligned']>first['aligned']+.5*observe and x['stream_rf']>first['stream_rf']+.5*observe,'Sustained RF processing fell';assert x['stock_bytes']>first['stock_bytes'] and x['extras']>first['extras'],'Forwarding stalled';assert x['pulse_relay']>first['pulse_relay'],'No pulse extras forwarded'
  s.update(state='active',verified_unix=time.time(),observed_seconds=time.monotonic()-began,backend=backend);save(D/'active.json',s);save(D/'observation.json',dict(first=first,last=x,samples=samples))
 except BaseException as e:rollback('activation_failure: '+repr(e));raise

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['activate','check','rollback','status']);p.add_argument('--observe',type=int,default=300);p.add_argument('--reason',default='manual');a=p.parse_args();R.mkdir(parents=True,exist_ok=True)
 if a.action=='status':print(json.dumps(dict(release=read(D/'active.json'),guard=read(R/'guard.json') if (R/'guard.json').exists() else {}),indent=2));return
 with (R/'lock').open('w') as own:
  try:fcntl.flock(own,fcntl.LOCK_EX|(fcntl.LOCK_NB if a.action=='check' else 0))
  except BlockingIOError:return
  # Same coordinator restart lock as the existing coherent/acquisition guard.
  # During activation this guard owns health supervision; the old guard skips.
  with Path('/run/adsb-rust-kernels-20261109/lock').open('w') as shared:
   try:fcntl.flock(shared,fcntl.LOCK_EX|(fcntl.LOCK_NB if a.action=='check' else 0))
   except BlockingIOError:return
   if a.action=='activate':assert a.observe>=180;activate(a.observe)
   elif a.action=='rollback':rollback(a.reason)
   else:
    try:check();(R/'error.json').unlink(missing_ok=True)
    except Exception as e:
     old=read(R/'error.json') if (R/'error.json').exists() else {};n=old.get('count',0)+1;save(R/'error.json',dict(count=n,error=repr(e),unix=time.time()))
     if n>=3:rollback('health_snapshot_failure: '+repr(e))
if __name__=='__main__':main()

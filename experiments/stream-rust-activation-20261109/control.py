"""Guard one hot-swapped Stream ELF. Never restart a production service."""
from pathlib import Path
import sys,json,hashlib,os,time,fcntl,subprocess,argparse,importlib.util
BASE=Path('/var/lib/adsb-rust-kernels-20261109');sys.path.insert(0,str(BASE));spec=importlib.util.spec_from_file_location('rust_base',BASE/'control.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
D=Path('/var/lib/adsb-stream-rust-20261109');R=Path('/run/adsb-stream-rust-20261109');B=Path('/home/pi/stream1090-shadow/build/stream1090');T='adsb-stream-rust-20261109.timer'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2)+'\n');os.replace(tmp,p)
 if str(p).startswith('/var/'):
  with p.open('rb') as f:os.fsync(f.fileno())
  fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def atomic(raw,s):
 p=B.with_suffix('.rust-new');p.write_bytes(raw);p.chmod(s['mode']);os.chown(p,s['uid'],s['gid'])
 with p.open('rb') as f:os.fsync(f.fileno())
 os.replace(p,B);fd=os.open(B.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def snapshot():
 x=base.snapshot();s=read('/run/adsb-rescue/status.json');f=read('/run/adsb-rescue/feed-status.json');st=s['stream1090'];x.update(stream_rf=st['counts'].get('processed_rf_seconds',0),stream_aligned=st['counts'].get('aligned_rf_seconds',0),stream_error=st.get('last_error'),stream_enabled=st['enabled'],stream_binary=st['binary'],stream_relay=f['counts'].get('relayed_stream1090',0));return x

def rollback(reason):
 s=read(D/'active.json')
 if s['state'] not in ['active','activating','restoring','rollback_failed']:return
 if sha(B) not in [s['after_sha256'],s['before_sha256']]:s.update(state='superseded_by_external_change',reason=reason);save(D/'active.json',s);subprocess.run(['systemctl','disable','--now',T],check=True);return
 s.update(state='restoring',reason=reason);save(D/'active.json',s)
 try:
  raw=(D/'original').read_bytes();assert hashlib.sha256(raw).hexdigest()==s['before_sha256'];atomic(raw,s);s.update(state='rolled_back',rolled_back_unix=time.time());save(D/'active.json',s);subprocess.run(['systemctl','disable','--now',T],check=True)
 except BaseException as e:s.update(state='rollback_failed',error=repr(e));save(D/'active.json',s);raise

def check():
 s=read(D/'active.json')
 if s['state'] in ['restoring','rollback_failed']:rollback('retry_incomplete_rollback');return
 if s['state'] not in ['active','activating']:return
 if sha(B)!=s['after_sha256']:rollback('binary_changed');return
 previous=read(R/'guard.json') if (R/'guard.json').exists() else {};x=snapshot();now=time.time();g=base.assess(x,previous,now)
 prev=previous.get('snapshot',{});g['last_stream_progress']=now if x['stream_rf']>prev.get('stream_rf',-1) or x['shadow_pid']!=prev.get('shadow_pid') else previous.get('last_stream_progress',now)
 if not x['stream_enabled'] or x['stream_binary']!=str(B):g['reasons'].append('stream_disabled_or_rerouted')
 if x['stream_error']:g['reasons'].append('stream_error: '+str(x['stream_error']))
 if now-g['last_stream_progress']>45:g['reasons'].append('stream_RF_stall')
 bad=previous.get('consecutive_failures',0)+1 if g['reasons'] else 0;g.update(unix=now,state='degraded' if bad else 'healthy',consecutive_failures=bad);save(R/'guard.json',g)
 if bad:
  save(D/('failure-'+str(time.time_ns())+'.json'),dict(previous=previous,current=g))
  if bad>=3:rollback(';'.join(g['reasons']))
 return g

def child_evidence(shadow):
 hits=[];parents={shadow};s=read('/run/adsb-rescue/status.json');parents.update(map(int,s['workers']['role_by_pid']))
 for parent in parents:
  for task in Path('/proc/'+str(parent)+'/task').glob('*'):
   try:children=(task/'children').read_text().split()
   except OSError:continue
   for p in children:
    try:
     exe=Path('/proc/'+p+'/exe');st=exe.stat()
     if str(exe.readlink())==str(B) and st.st_ino==B.stat().st_ino:hits.append(dict(pid=int(p),inode=st.st_ino,unix=time.time()))
    except OSError:pass
 return hits

def activate(observe):
 s=read(D/'active.json');assert s['state']=='prepared' and sha(B)==s['before_sha256'];first=snapshot();assert first['stream_enabled'] and not base.assess(first,None,time.time())['reasons'];assert first['fr24_connected'] and not first['stream_error']
 s.update(state='activating',activated_unix=time.time(),before=first);save(D/'active.json',s);subprocess.run(['systemctl','enable','--now',T],check=True)
 try:
  raw=(D/'candidate').read_bytes();assert hashlib.sha256(raw).hexdigest()==s['after_sha256'];atomic(raw,s);began=time.monotonic();samples=[];hits=[];next_check=0
  while time.monotonic()-began<observe:
   hits.extend(child_evidence(first['shadow_pid']))
   if time.monotonic()>=next_check:
    g=check();assert g and not g['reasons'],g;x=g['snapshot'];assert x['protected_pids']==first['protected_pids'] and x['shadow_pid']==first['shadow_pid'];assert x['config_hashes']==first['config_hashes'] and x['methods']==first['methods'] and x['worker_config']==first['worker_config'] and x['samples']==first['samples'] and x['gain']==first['gain'];samples.append(g);save(R/'observation.json',dict(samples=samples,child_evidence=hits));next_check=time.monotonic()+10
   time.sleep(.1)
  last=snapshot();assert last['stream_rf']>=first['stream_rf']+observe*.5 and last['stock_bytes']>first['stock_bytes'] and last['stream_relay']>first['stream_relay'] and hits,'Stream processing/forwarding/mapping did not progress';assert last['stream_aligned']>first['stream_aligned'];s.update(state='active',verified_unix=time.time(),observed_seconds=time.monotonic()-began);save(D/'active.json',s);save(D/'observation.json',dict(first=first,last=last,samples=samples,child_evidence=hits))
 except BaseException as e:rollback('activation_failure: '+repr(e));raise

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['activate','check','rollback','status']);p.add_argument('--observe',type=int,default=300);p.add_argument('--reason',default='manual');a=p.parse_args();R.mkdir(parents=True,exist_ok=True)
 if a.action=='status':print(json.dumps(dict(release=read(D/'active.json'),guard=read(R/'guard.json') if (R/'guard.json').exists() else {}),indent=2));return
 with (R/'lock').open('w') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|(fcntl.LOCK_NB if a.action=='check' else 0))
  except BlockingIOError:return
  if a.action=='activate':assert a.observe>=180;activate(a.observe)
  elif a.action=='rollback':rollback(a.reason)
  else:
   try:check();(R/'error.json').unlink(missing_ok=True)
   except Exception as e:
    old=read(R/'error.json') if (R/'error.json').exists() else {};n=old.get('count',0)+1;save(R/'error.json',dict(count=n,error=repr(e),unix=time.time()))
    if n>=3:rollback('health_snapshot_failure: '+repr(e))
if __name__=='__main__':main()

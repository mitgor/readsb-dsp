#!/usr/bin/env python3
"""Install reviewed relay controls without restarting receiver/decoder/feeders."""
import argparse,ast,hashlib,json,os,pathlib,runpy,shutil,subprocess,time,urllib.request
P=pathlib.Path

def main(stage):
 G=runpy.run_path('/usr/local/sbin/adsb-stream1090-lowlatency-mode');A=runpy.run_path('/usr/local/sbin/adsb-arrival-relay-mode');R=G['ROOT'];before=G['snapshot']();G['check'](G['read'](G['STATE']),before);A['check'](A['read'](A['STATE']));G['capture']();nstate=G['read'](G['STATE']);assert nstate['state']=='active'
 # The portability update only renames the import; inference is identical.
 for rel in ['lowlatency_stream.py','latency_core/completion_bridge.py']:
  new=(stage/rel).read_text();old=(R/rel).read_text();assert new.replace('stream1090_compare import','stream1090_shadow import')==old,rel
 old=ast.parse((R/'stream1090_shadow.py').read_text());new=ast.parse((stage/'stream1090_compare.py').read_text())
 for name in ['compare','valid_df17']:
  f=lambda tree:next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
  assert ast.dump(f(old))==ast.dump(f(new)),name
 files={R/'web_control.py':stage/'web_control.py',R/'relay_control.py':stage/'relay_control.py',R/'stream1090_compare.py':stage/'stream1090_compare.py',R/'lowlatency_stream.py':stage/'lowlatency_stream.py',R/'latency_core/completion_bridge.py':stage/'latency_core/completion_bridge.py',P('/usr/local/sbin/adsb-relay-select'):stage/'select.py',P('/usr/share/adsb-rescue/index.html'):stage/'statistics.html'}
 for name in ['arrival','ordered']:files[P('/etc/systemd/system')/f'adsb-relay-{name}-select.service']=stage/(name+'-select.service')
 backup=P('/var/backups')/('adsb-relay-controls-'+str(time.time_ns()));backup.mkdir(mode=0o700);records={}
 for i,(dest,src) in enumerate(files.items()):
  st=dest.stat() if dest.exists() else None;rec=dict(existed=st is not None,uid=st.st_uid if st else 0,gid=st.st_gid if st else 0,mode=(st.st_mode&0o777) if st else (0o755 if dest.name=='adsb-relay-select' else 0o644),backup=str(i),new_sha256=G['sha'](src))
  if st:shutil.copy2(dest,backup/str(i));rec['old_sha256']=G['sha'](dest)
  records[str(dest)]=rec
 G['save'](backup/'files.json',records);G['save'](backup/'native-state.private.json',nstate)
 ctl=lambda *args:subprocess.run(['systemctl',*args],check=True,timeout=45)
 timers=['adsb-arrival-relay-guard.timer','adsb-stream1090-lowlatency-guard.timer'];services=['adsb-arrival-relay-guard.service','adsb-stream1090-lowlatency-guard.service']
 try:
  ctl('stop',*timers,*services)
  release=P('/var/lib/adsb-arrival-relay/release');existing=release.exists()
  if not existing:(release/'arrival').mkdir(parents=True,mode=0o700)
  manifest={}
  for name in A['NAMES']:
   assert G['sha'](R/name)==A['read'](A['STATE'])['installed'][name]
   if existing:assert G['sha'](release/'arrival'/name)==G['sha'](R/name),'Existing release changed: '+name
   else:G['atomic'](release/'arrival'/name,(R/name).read_bytes(),dict(uid=0,gid=0,mode=0o644))
   manifest['arrival/'+name]=G['sha'](R/name)
  if existing:assert G['read'](release/'manifest.json')==manifest,'Existing release manifest changed'
  else:G['save'](release/'manifest.json',manifest)
  for dest,src in files.items():G['atomic'](dest,src.read_bytes(),records[str(dest)])
  for rel in ['lowlatency_stream.py','latency_core/completion_bridge.py','stream1090_compare.py']:nstate['installed'][str(R/rel)]=G['sha'](R/rel)
  G['save'](G['STATE'],nstate);ctl('daemon-reload');ctl('restart','adsb-rescue-web.service')
  deadline=time.time()+15
  while True:
   try:
    with urllib.request.urlopen('http://127.0.0.1:8911/readsb-dsp/api/relay',timeout=5) as f:status=json.load(f)
    break
   except (OSError,ValueError):
    if time.time()>deadline:raise
    time.sleep(.3)
  assert status['available'] and status['actual_holdback_s']==0 and status['native_backend']=='incremental_native',status
  after=G['snapshot']();G['healthy'](before,after);G['check'](nstate,after);A['check'](A['read'](A['STATE']));G['capture']();G['save'](backup/'deployment.private.json',dict(before=before,after=after,relay=status,release=str(release),success=True))
  print(json.dumps(dict(success=True,backup=str(backup),holdback_s=0,native='incremental_native',protected_pids_unchanged=True)))
 except BaseException as exc:
  for dest,rec in records.items():
   p=P(dest)
   if p.exists() and G['sha'](p) not in [rec['new_sha256'],rec.get('old_sha256')]:continue
   if rec['existed']:G['atomic'](p,(backup/rec['backup']).read_bytes(),rec)
   else:p.unlink(missing_ok=True)
  G['save'](G['STATE'],G['read'](backup/'native-state.private.json'));ctl('daemon-reload');ctl('restart','adsb-rescue-web.service');G['save'](backup/'failure.json',dict(error=repr(exc)));raise
 finally:ctl('start',*timers)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stage',type=P,required=True);main(p.parse_args().stage)

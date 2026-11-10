"""Filesystem rollback and two-strike guard controls, wholly inside a temp root."""
import argparse,importlib.util,importlib.machinery,tempfile,json,os,hashlib,types
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--module',type=Path,required=True);a=p.parse_args()
spec=importlib.util.spec_from_loader('activation_test',importlib.machinery.SourceFileLoader('activation_test',str(a.module)));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='stream-native-rollback-') as d:
 r=Path(d);m.ROOT=r;m.STATE=r/'state.json';m.CFG=r/'cfg.json';m.GUARD_RUNTIME=r/'guard.json';b=r/'backup';b.mkdir();old=r/'method.py';old.write_text('new native wrapper');added=r/'native.so';added.write_text('new library');(b/'file-0').write_text('old executable wrapper')
 records={str(old):{'existed':True,'backup':'file-0','sha256':m.sha(b/'file-0'),'uid':os.getuid(),'gid':os.getgid(),'mode':0o644},str(added):{'existed':False,'backup':'file-1','uid':os.getuid(),'gid':os.getgid(),'mode':0o644}}
 m.save(b/'files.json',records);m.save(m.STATE,{'state':'active','backup':str(b),'installed_sha256':{str(old):m.sha(old),str(added):m.sha(added)}})
 m.runtime=lambda:{'updated_unix':m.time.time(),'threads_alive':True}
 calls=[]
 def fake_run(cmd,**kwargs):
  calls.append(cmd);assert cmd==['systemctl','is-active','adsb-rescue-shadow'],'Rollback must not restart a healthy coordinator';return types.SimpleNamespace(stdout='active\n')
 m.subprocess=types.SimpleNamespace(run=fake_run)
 m.rollback('forced test')
 assert old.read_text()=='old executable wrapper' and not added.exists()
 assert m.read(m.CFG)['backend']=='executable' and m.read(m.STATE)['state']=='rolled_back'
 assert m.read(m.STATE)['coordinator_restarted'] is False
 # Guard may read health but must not roll back on a single transient check.
 m.save(m.STATE,{'state':'active','boot':m.boot(),'before':{},'bad_checks':0})
 m.snapshot=lambda:{};m.runtime=lambda:{'stream1090':{}}
 def bad_health(*args):raise RuntimeError('forced isolated health failure')
 m.healthy=bad_health;rolled=[];m.rollback=lambda why:rolled.append(why)
 m.guard();assert not rolled and m.read(m.STATE)['bad_checks']==1
 m.guard();assert len(rolled)==1 and m.read(m.STATE)['bad_checks']==2
print(json.dumps({'filesystem_restore_exact':True,'fallback_persistent':True,'no_restart_when_coordinator_healthy':True,'two_strike_guard':True,'production_mutations':[]}))

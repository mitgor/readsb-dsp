#!/usr/bin/env python3
"""Default acquisition/EM Rust backends, independent guarded rollback.
Requires the established coherent deployment health helper. Never enables methods.
"""
import json,os,runpy,shutil,subprocess,time
from pathlib import Path
base=runpy.run_path('/usr/local/sbin/adsb-coherent-rust-mode')
g=base['snapshot'].__globals__
ROOT=g['ROOT'];STATE=Path('/var/lib/adsb-rust-methods/active.json');RUNTIME=Path('/run/adsb-rust-methods/guard.json')
FILES={f'src/rescue/{n}':f'src/rescue/{n}' for n in ['coherent_extended_opt.py','research_science.py','acquisition_rust.rs','science_em_rust.rs']}
FILES.update({f'src/rescue/{n}':f'candidate/{n}' for n in ['_acquisition_rust.so','_science_em_rust.so','_science.so']})
g.update(STATE=STATE,RUNTIME=RUNTIME,FILES=FILES)

def activate(stage,observe):
 read,sha,save,snapshot,healthy,atomic,rollback=(g[k] for k in ['read','sha','save','snapshot','healthy','atomic','rollback'])
 if STATE.exists():assert read(STATE)['state']=='rolled_back','Release already active/incomplete'
 proof=read(stage/'release.json');controls=read(stage/'controls.json');packets=read(stage/'packets.json')
 assert proof['wrapper_parity'] and proof['c_sequence_and_combined_smoke']
 assert all(x['exact_all_arrays'] for x in proof['em'].values())
 assert controls['exact_scoring_and_candidate_cases']>=1201 and controls['noise_crc_valid']==0
 assert all(x['exact_candidate_and_all_decoder_arrays'] for x in packets['budgets'].values())
 for name,expected in proof['candidate_sha256'].items():assert sha(stage/'candidate'/name)==expected
 assert sha(ROOT/'src/rescue/_pipeline_extended_neon.so')==sha(stage/'parity/c.so'),'Acquisition baseline changed'
 before=snapshot();healthy(before,before)
 assert before['crc_archive']['disk_bytes']+before['crc_archive']['ram_bytes']+8*1024**2<512*1024**2,'Insufficient shutdown-save capacity'
 backup=Path('/var/backups')/('adsb-rust-methods-'+str(time.time_ns()));backup.mkdir(mode=0o700);records={};hashes={}
 for index,(dest,source) in enumerate(FILES.items()):
  p=ROOT/dest;stat=p.stat() if p.exists() else p.parent.stat();record={'existed':p.exists(),'backup':f'file-{index}','mode':stat.st_mode&0o777 if p.exists() else 0o644,'uid':stat.st_uid,'gid':stat.st_gid}
  if p.exists():shutil.copy2(p,backup/record['backup']);record['sha256']=sha(p)
  records[str(p)]=record;hashes[dest]=sha(stage/source)
 save(backup/'files.json',records)
 report={'before':before,'backup':str(backup),'installed_sha256':hashes,'samples':[],'activated':False,'policy':'Backend default only; method activation and routing unchanged. EM research entrypoint only; sequence/combined remain C.'}
 save(backup/'deployment.json',report);save(STATE,{'state':'activating','backup':str(backup),'installed_sha256':hashes})
 try:
  for dest,source in FILES.items():atomic(ROOT/dest,(stage/source).read_bytes(),records[str(ROOT/dest)])
  smoke="from rescue.coherent_extended_opt import backend_status as a;from rescue.research_science import backend_status as b,em_library,library;assert a()=='rust';assert b()=={'em':'rust','sequence':'c','em_sequence':'c'};assert em_library() is not library();print(a(),b())"
  report['smoke']=subprocess.check_output([str(ROOT/'.venv/bin/python'),'-c',smoke],env={**os.environ,'PYTHONPATH':str(ROOT/'src')},text=True)
  switched=time.time();subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
  for _ in range(45):
   s=snapshot()
   if s['started_unix']>switched and s['aligned_seconds']>=5:break
   time.sleep(2)
  else:raise RuntimeError('Workers failed to become ready')
  since=time.time();first=s
  while True:
   healthy(before,s);g['mapped'](s);report['samples'].append(s);save(backup/'deployment.json',report)
   if time.time()-since>=observe:break
   time.sleep(10);s=snapshot()
  assert s['aligned_seconds']-first['aligned_seconds']>=observe*.8,'RF throughput fell'
  for key in ['stock_bytes_relayed','dsp_frames_relayed','relayed_coherent']:assert s['feed']['counts'][key]>first['feed']['counts'][key],key+' stalled'
  for dest in FILES:assert sha(ROOT/dest)==hashes[dest]
  report['activated']=True;save(backup/'deployment.json',report)
  save(STATE,{'state':'active','backup':str(backup),'installed_sha256':hashes,'activated_unix':time.time()})
  print(json.dumps({'activated':True,'backup':str(backup),'protected_pids_unchanged':True,'method_switches_unchanged':True,'aligned_seconds':s['aligned_seconds']-first['aligned_seconds']}))
 except BaseException as error:
  report['error']=repr(error);rollback('activation: '+repr(error));report['rolled_back']=True;save(backup/'deployment.json',report);raise

g['activate']=activate
if __name__=='__main__':g['main']()

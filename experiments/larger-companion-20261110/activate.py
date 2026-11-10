"""Add only the validated November 10 companion, original-first; web/SDR untouched."""
import json,hashlib,os,shutil,subprocess,time,runpy,sys
from pathlib import Path
D=Path('/var/lib/adsb-companion-20261110-v2');ROOT=Path('/home/pi/adsb-neural-rescue');SOURCE=ROOT/'src/rescue/model_cascade.py'
MODEL=ROOT/'models/candidates/retrain-20261110/dsp/tiny-rf-v1.onnx'
G=runpy.run_path('/usr/local/sbin/adsb-coherent-rust-mode')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,value):
 p=D/name;tmp=p.with_suffix('.tmp')
 with tmp.open('w') as f:json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def restore(force=False):
 if not (D/'state.json').exists():return
 state=json.loads((D/'state.json').read_text())
 if state['state']!='activating' and not (force and state['state']=='active'):return
 if sha(SOURCE)!=state['installed_sha']:raise RuntimeError('External source change; no overwrite')
 if sha(ROOT/'src/rescue/runtime.py')!='fd6d9a63326ba9fbfc2648413027683618c7858d7a250f404a454eca91b43202':raise RuntimeError('External runtime change; no overwrite')
 shutil.copy2(D/'runtime.py.before',ROOT/'src/rescue/runtime.py');shutil.copy2(D/'model_cascade.py.before',SOURCE);subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
 save('state.json',{**state,'state':'rolled_back','at':time.time()})
def main():
 if '--restore-unconfirmed' in sys.argv:return restore()
 if '--rollback' in sys.argv:return restore(force=True)
 assert not (D/'state.json').exists()
 before=G['snapshot']();G['healthy'](before,before)
 archive=before['crc_archive'];assert archive['disk_bytes']+archive['ram_bytes']+16*1048576<512*1048576
 assert sha('/tmp/companion-retrain-20261110.onnx')=='85bb0a3560120e5476d5080b1e829c3badc2da68ea925f7b55da75afbc455906'
 assert "retrain-20261110" not in SOURCE.read_text()
 assert not MODEL.exists() or sha(MODEL)=='85bb0a3560120e5476d5080b1e829c3badc2da68ea925f7b55da75afbc455906'
 shutil.copy2(ROOT/'src/rescue/runtime.py',D/'runtime.py.before');shutil.copy2(SOURCE,D/'model_cascade.py.before');save('before.json',before)
 MODEL.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile('/tmp/companion-retrain-20261110.onnx',MODEL);os.chmod(MODEL,0o644)
 proposed=Path('/tmp/companion-model-cascade-after.py').read_bytes();installed=hashlib.sha256(proposed).hexdigest()
 state={'state':'activating','installed_sha':installed,'candidate_sha':sha(MODEL),'at':time.time()};save('state.json',state)
 try:
  shutil.copyfile('/tmp/companion-runtime-after.py',ROOT/'src/rescue/runtime.py')
  SOURCE.write_bytes(proposed)
  subprocess.run([str(ROOT/'.venv/bin/python'),'-c',"from rescue.model_cascade import production_paths,cascade_decoder; p=production_paths('.'); assert len(p)==4; cascade_decoder(p); print('four-model cascade loaded')"],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'},check=True)
  began=time.time();subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
  for _ in range(40):
   s=G['snapshot']()
   if s['started_unix']>=began-1 and s['aligned_seconds']>0:break
   time.sleep(2)
  else:raise RuntimeError('Fresh decoder did not become ready')
  samples=[];first=s
  for _ in range(30):
   s=G['snapshot']();checked=s
   if int(s['fr24'].get('feed_num_ac_tracked') or 0)==0:checked={**s,'fr24':{**s['fr24'],'feed_last_ac_sent_time':int(time.time())}}
   G['healthy'](before,checked)
   assert sha(SOURCE)==installed
   cap=json.load(open('/run/adsb-far-capture/status.json'));assert cap['config']['disk_limit_bytes']==5000000000 and not cap['error']
   samples.append(s);save('observation.json',samples);time.sleep(5)
  assert s['aligned_seconds']>first['aligned_seconds'] and s['feed']['counts']['stock_bytes_relayed']>first['feed']['counts']['stock_bytes_relayed']
  save('state.json',{**state,'state':'active','confirmed_unix':time.time(),'aligned_progress':s['aligned_seconds']-first['aligned_seconds'],'protected_pids_unchanged':True})
 except Exception:
  restore();raise
if __name__=='__main__':main()

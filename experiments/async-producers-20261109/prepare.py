#!/usr/bin/env python3
import pathlib,json,subprocess,shutil,os,base64,io,tarfile
R=pathlib.Path(__file__).resolve().parents[2];P=pathlib.Path('/Users/mit/Documents/!project/adsb-neural-rescue');raw=P/'data/raw/async-producers-20261109/files';dest=P/'results/async-producers-20261109';dest.mkdir(parents=True,exist_ok=True)
offset=float(subprocess.check_output(['ssh','adsb-rpi','python3','-c','"import time;print(time.time()-time.monotonic())"'],text=True));timing=dict(clock_offset_s=offset,recorded_after_capture=True,limitation='Offset sampled at staging, not RF capture. Sample identities do not depend on wall-clock estimate.')
mac=dest/'mac-runtime';assert not mac.exists();shutil.copytree(raw/'runtime',mac);shutil.copytree(raw/'capture-v3',mac/'capture');(mac/'timing.json').write_text(json.dumps(timing))
libs=P/'data/transfer/companion-validation-20261104/runtime/src/rescue'
for d in [P/'src/rescue',libs]:
 for p in d.glob('*.so'):
  if p.read_bytes()[:4]==b'\xcf\xfa\xed\xfe':shutil.copy2(p,mac/'src/rescue'/p.name)
# Never try loading an ELF library in the Mac copy.
for p in (mac/'src/rescue').glob('*.so'):
 if p.read_bytes()[:4]!=b'\xcf\xfa\xed\xfe':p.unlink()
shutil.copy2(P/'data/transfer/retrain-companion-20261029/stream1090/build/stream1090',mac/'stream1090');(mac/'stream1090').chmod(0o700)
# New isolated target code tree. RF is an immutable owned capture already backed up on Mac.
files={}
for name in ['integration.py','replay.py','health.py','protected.py']:
 p=R/'experiments/async-producers-20261109'/name
 if p.exists():files['experiments/async-producers-20261109/'+name]=base64.b64encode(p.read_bytes()).decode()
for folder in ['async-relay-20261030','latency-publication-20261030','completion-bridge-20261030']:
 for p in (R/'experiments'/folder).glob('*.py'):files['experiments/'+folder+'/'+p.name]=base64.b64encode(p.read_bytes()).decode()
script='FILES='+repr(files)+'\nTIMING='+repr(timing)+'''
import pathlib,shutil,os,pwd,base64,json,hashlib
root=pathlib.Path('/home/pi/adsb-neural-rescue');stage=pathlib.Path('/run/adsb-async-producers-replay-20261109');assert not stage.exists();stage.mkdir();shutil.copytree(root/'src/rescue',stage/'src/rescue',ignore=shutil.ignore_patterns('__pycache__'))
for n in ['tiny-fp32.onnx','pulse-sequence.json','pulse-discriminant.json','candidates/dsp-20261025/tiny-rf-v1.onnx','candidates/improvement-raw-20261027/tiny-rf-v1.onnx']:
 p=stage/'models'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/'models'/n,p)
for n,p in [('worker-config.json','/etc/default/adsb-rescue-workers.json'),('method-config.json','/etc/default/adsb-rescue.json')]:shutil.copy2(p,stage/n)
shutil.copy2('/home/pi/stream1090-shadow/build/stream1090',stage/'stream1090');(stage/'stream1090').chmod(0o700)
(stage/'capture').symlink_to('/run/adsb-async-producers-20261109-v3-capture/data');(stage/'timing.json').write_text(json.dumps(TIMING))
for n,b in FILES.items():p=stage/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(b))
u=pwd.getpwnam('pi')
for p in [stage,*stage.rglob('*')]:
 if not p.is_symlink():os.chown(p,u.pw_uid,u.pw_gid)
print(stage)
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=script,text=True));print('Mac stage',mac)

import json,shutil,hashlib,tarfile
from pathlib import Path
D=Path('/dev/shm/adsb-larger-companion-20261110');root=D.resolve()
with tarfile.open(D/'input.tar.gz') as tar:
 for m in tar.getmembers():
  assert m.isfile() and (root/m.name).resolve().is_relative_to(root)
  tar.extract(m,root)
for p,h in json.loads((D/'input-manifest.json').read_text()).items():assert hashlib.sha256((D/p).read_bytes()).hexdigest()==h
runtime=D/'data/transfer/larger-companion-20261110/runtime';runtime.mkdir(parents=True)
shutil.copytree('/home/pi/adsb-neural-rescue/src',runtime/'src',ignore=shutil.ignore_patterns('__pycache__','*.before*','*.bak'))
source=runtime/'src/rescue/runtime.py';s=source.read_text();a="('frozen','dsp_companion','raw_companion','retrained_20261110_companion')";assert a in s;s=s.replace(a,"('frozen','dsp_companion','raw_companion','retrained_20261110','previous_best_offline','wide_candidate')");source.write_text(s)
# Benchmark explicitly appends the new production companion to the frozen three.
shutil.copyfile(D/'base-model-cascade.py',runtime/'src/rescue/model_cascade.py')
selection=json.loads((D/'selected.json').read_text());candidate=D/selection['model'];candidate.parent.mkdir(parents=True);shutil.copyfile(D/'candidate.onnx',candidate);assert hashlib.sha256(candidate.read_bytes()).hexdigest()==selection['sha256']
out=D/'results/larger-companion-20261110';out.mkdir(parents=True);shutil.copyfile(D/'selected.json',out/'selected.json')
stream=D/'data/transfer/retrain-companion-20261029/stream1090/build/stream1090';stream.parent.mkdir(parents=True);shutil.copy2('/home/pi/stream1090-shadow/build/stream1090',stream)
manifest={str(p.relative_to(runtime)):hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.rglob('*') if p.is_file()};(D/'target-source-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Input hashes verified; copied actual target libraries and executable, no SDR access')

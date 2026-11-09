"""Publish only redacted static report through established receiver HTTP access."""
from pathlib import Path
import json,subprocess,shlex,hashlib,urllib.request
D=Path(__file__).resolve().parents[2]/'validation/stream-rust-activation-20261109';names=['report.html','report.md','summary.json'];payload={n:(D/n).read_text() for n in names}
code='''from pathlib import Path
import json,sys,os
D=Path('/usr/share/adsb-rescue/stream-rust-activation-20261109');D.mkdir(exist_ok=True);D.chmod(0o755)
x=json.load(sys.stdin);assert set(x)=={'report.html','report.md','summary.json'}
for n,s in x.items():
 p=D/n;p.write_text(s);p.chmod(0o644)
 with p.open('rb') as f:os.fsync(f.fileno())
'''
subprocess.run(['ssh','adsb-rpi','sudo python3 -c '+shlex.quote(code)],input=json.dumps(payload).encode(),check=True)
for n in names:
 b=urllib.request.urlopen('http://192.168.2.195/neural-rescue/stream-rust-activation-20261109/'+n,timeout=10).read();assert hashlib.sha256(b).digest()==hashlib.sha256((D/n).read_bytes()).digest()
print('Published redacted report; all HTTP checksums match.')

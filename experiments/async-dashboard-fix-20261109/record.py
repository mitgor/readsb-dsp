"""Save private before/after evidence and redacted public repair result."""
from pathlib import Path
import subprocess,json,tarfile,io,hashlib,os,html,urllib.request
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/async-dashboard-fix-20261109');R=Path(__file__).resolve().parents[2];O=R/'validation/async-dashboard-fix-20261109';O.mkdir(parents=True,exist_ok=True)
code=r'''
from pathlib import Path
import tarfile,io,json,hashlib,sys,subprocess
P=Path;D=P('/var/lib/adsb-async-dashboard-fix-20261109');paths=list(D.glob('*'))+[P('/home/pi/adsb-neural-rescue/src/rescue')/n for n in ['async_live_engine.py','async_live_shadow.py','web_control.py','method_metrics.py']]+[P('/run/adsb-rescue/status.json'),P('/run/adsb-rescue/feed-status.json'),P('/run/adsb-far-capture/status.json'),P('/run/adsb-async-live-20261109/status.json')];m={};b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w:gz') as t:
 for p in paths:
  assert p.is_file() and not p.is_symlink();raw=p.read_bytes();name=str(p).lstrip('/');i=tarfile.TarInfo(name);i.size=len(raw);t.addfile(i,io.BytesIO(raw));m[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 raw=json.dumps(m).encode();i=tarfile.TarInfo('manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
sys.stdout.buffer.write(b.getvalue())
'''
raw=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode(),timeout=30);p=D/'evidence.tar.gz';assert not p.exists();p.write_bytes(raw);p.chmod(0o600)
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as t:
 manifest=json.load(t.extractfile('manifest.json'))
 for n,v in manifest.items():
  b=t.extractfile(n).read();assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256']
receipt=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),verified_members=len(manifest));(D/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
for p in D.iterdir():
 with p.open('rb') as f:os.fsync(f.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
s=json.loads((D/'metrics-check.json').read_text());(O/'summary.json').write_text(json.dumps(s,indent=2)+'\n');m=s['after']
md=f'''# Dashboard controls and Stream1090 CPU accounting fixed

The settings API returned HTTP 500 because the long-running controls service retained an old capture-policy validator loaded on October 29. A fresh process accepted the current 180 nm / 5 GB policy. Restarting the controls service loaded the current policy without changing capture settings.

The asynchronous integration omitted the old synchronous call to MethodMetrics.record_external. Stream1090 child CPU was measured but discarded when its independent future completed. The engine now charges it exactly once, including failed/unaligned or discarded-old-epoch work, and exposes a matching independent stream_child_cpu_s audit counter. Decoder algorithms, method switches and models are unchanged.

Verified through HTTP: GET settings 200; same-origin no-op POST 200 with byte-identical configurations and the same revision. No-op Apply now returns before rewriting files or restarting workers, preserving rollback ownership. Three regression tests passed on Mac and Pi: completed child charged once, old-epoch work charged, and no-op settings preserve bytes/revision.

| Stream1090 verification sample | Value |
|---|---:|
| Measured child CPU | {m['cpu_seconds']:.3f} s |
| Mean CPU, one core = 100% | {m['mean_core_percent']:.2f}% |
| Worker/child CPU share | {m['cpu_share_percent']:.2f}% |
| Attributed extras | {m['additional_packets']} |
| CPU per attributed extra | {m['cpu_ms_per_additional']:.2f} ms |
| Relative cost | {m['relative_cpu_per_detection']:.2f}× |

CPU increased across successive status reports and exactly matched the independent engine audit. Other method shares and relative costs now use the corrected denominator. This is attributed CPU cost, not an ablation measurement or electrical power.

The DSP coordinator and controls service restarted for this fix; dashboard CPU/detection counters began a new interval. Historical missing CPU is not retroactively reconstructed. readsb, FR24, the asynchronous relay, ADSBx and the RF collector retained their PIDs. SIC remains off; the persistent rollback guard is enabled and healthy. Gain, models, RF collection limits and 12-hour save policy are unchanged. Existing capture/CRC archives remain intact.

Neural development collection remains active: stock-confirmed >=180 nm snippets, original RF, and stock/unified Beast journals, bounded by the existing 5 GB cap. Qualification is still required before training; incomplete burst coverage stays flagged. The general historical experimental logger being off does not disable the dedicated far-training collector.

Private before/after source, metrics and status evidence is checksum-verified and durably saved on the Mac. Raw collection data and configurations are not published here.
'''
(O/'report.md').write_text(md);(O/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Dashboard fix</title><style>body{font:17px/1.5 system-ui;max-width:1000px;margin:30px auto;padding:20px}pre{white-space:pre-wrap;font:inherit}</style><pre>'+html.escape(md)+'</pre>')
remote='/usr/share/adsb-rescue/async-dashboard-fix-20261109';subprocess.run(['ssh','adsb-rpi','sudo','mkdir','-p',remote],check=True)
for n in ['report.html','summary.json']:
 b=(O/n).read_bytes();subprocess.run(['ssh','adsb-rpi','sudo','tee',remote+'/'+n],input=b,stdout=subprocess.DEVNULL,check=True);assert hashlib.sha256(urllib.request.urlopen('http://192.168.2.195/neural-rescue/async-dashboard-fix-20261109/'+n).read()).hexdigest()==hashlib.sha256(b).hexdigest()
print(json.dumps(receipt))

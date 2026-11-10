"""Read-only receiver health; never include feeder credentials."""
import json,time,hashlib,subprocess,urllib.request
from pathlib import Path
ROOT=Path('/home/pi/adsb-neural-rescue')
def snapshot():
 s=json.loads(Path('/run/adsb-rescue/status.json').read_text());m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=3));assert m['feed_status']=='connected' and str(m['rx_connected'])=='1'
 files=[Path('/home/pi/stream1090-shadow/build/stream1090')]+list((ROOT/'src/rescue').glob('*.py'))+list((ROOT/'src/rescue').glob('*.so'))+list((ROOT/'models').rglob('*.onnx'))+list((ROOT/'models').glob('*.json'))+[Path('/etc/default/adsb-rescue.json'),Path('/etc/default/adsb-rescue-workers.json'),Path('/etc/default/readsb'),Path('/etc/fr24feed.ini'),Path('/etc/default/adsb-far-capture.json')]
 f=json.loads(Path('/run/adsb-rescue/feed-status.json').read_text());c=json.loads(Path('/run/adsb-far-capture/status.json').read_text());local=s['health']['local'];assert f['stock_connected'] and f['fr24_routed'] and c['disk_limit_bytes']==5000000000 and not c['error']
 return dict(pids={u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in ['readsb','fr24feed','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture','adsbexchange-feed']},hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()},gain=s['health']['gain_db'],methods=s['method_switches'],stock_loss={k:local.get(k,0) for k in ['samples_lost','samples_dropped']},holdback_s=f['holdback_s'],cap=c['disk_limit_bytes'])

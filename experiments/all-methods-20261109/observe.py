#!/usr/bin/env python3
import json,subprocess,time,datetime,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v1',choices=['v1','v2','v3']);p.add_argument('--samples',type=int,default=19);a=p.parse_args()
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/all-methods-20261109');D=D if a.attempt=='v1' else D.with_name(D.name+'-'+a.attempt);D.mkdir(parents=True,exist_ok=True)
code=r'''
import pathlib,json,time,subprocess,urllib.request
R=pathlib.Path('/run/adsb-rescue');s=json.loads((R/'status.json').read_text());f=json.loads((R/'feed-status.json').read_text());m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=5));capture=json.loads(pathlib.Path('/run/adsb-far-capture/status.json').read_text())
def optional(p):return json.loads(pathlib.Path(p).read_text()) if pathlib.Path(p).exists() else None
print(json.dumps(dict(unix=time.time(),status=s,relay=f,guard=optional('/run/adsb-all-methods-20261109/status.json'),outcome=optional('/var/lib/adsb-all-methods-20261109/outcome.json'),activation=optional('/var/lib/adsb-all-methods-20261109/activation.json'),fr24={k:m.get(k) for k in ['feed_status','rx_connected','num_messages']},capture={k:capture.get(k) for k in ['enabled','error','disk_limit_bytes']},pids={u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in ['readsb','fr24feed','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture']})))
'''
if a.attempt!='v1':code=code.replace('20261109','20261109-'+a.attempt)
rows=[]
for i in range(a.samples):
 r=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True,timeout=15));rows.append(r)
 (D/'observation.json').write_text(json.dumps(rows,indent=2)+'\n')
 s=r['status'];print(json.dumps(dict(sample=i,enabled=[k for k,v in s['method_switches'].items() if v],processing=[s['mean_processing_s'],s['max_recent_processing_s']],pending=s['workers']['pending_jobs'],completed=s['workers']['completed_rf_seconds'],fr24=r['fr24']['feed_status'],guard=r['guard'],outcome=r['outcome'])),flush=True)
 if r['outcome']:break
 if i<a.samples-1:time.sleep(10)

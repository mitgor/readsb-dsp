"""Read only receiver RRDs, never flush/restart/change services."""
import json,math,re,subprocess,time
from pathlib import Path
root=Path('/run/collectd/localhost');wanted=[]
for folder,names in [('dump1090-localhost',['dump1090_misc-gain_db','dump1090_dbfs-signal','dump1090_dbfs-noise','dump1090_messages-strong_signals','dump1090_cpu-demod','dump1090_cpu-reader','dump1090_cpu-background']),('aggregation-cpu-average',['cpu-idle','cpu-user','cpu-system','cpu-wait','cpu-softirq','cpu-interrupt','cpu-steal','cpu-nice']),('table-localhost',['gauge-cpu_temp']),('interface-wlan0',['if_octets','if_errors','if_dropped'])]:
 for name in names:wanted.append(root/folder/(name+'.rrd'))
# Use explicit ISO-based UTC epoch conversion instead of hand-written constants.
import datetime
start=int(datetime.datetime(2026,10,26,tzinfo=datetime.timezone.utc).timestamp());end=int(datetime.datetime(2026,10,29,tzinfo=datetime.timezone.utc).timestamp())
out={'collected_unix':time.time(),'rrd':{},'missing':[]}
for p in wanted:
 if not p.exists():out['missing'].append(str(p.relative_to(root)));continue
 run=subprocess.run(['rrdtool','fetch',str(p),'AVERAGE','--start',str(start),'--end',str(end),'--resolution','180'],capture_output=True,text=True,check=True)
 rows=[]
 for line in run.stdout.splitlines():
  m=re.match(r'^(\d+):\s+(.+)',line)
  if m:rows.append([int(m[1]),[float(v) if math.isfinite(float(v)) else None for v in m[2].split()]])
 out['rrd'][str(p.relative_to(root))]={'columns':run.stdout.splitlines()[0].split(),'rows':rows}
print(json.dumps(out))

"""Finite read-only post-activation socket parity and health observation."""
import socket,selectors,time,json,collections,bisect,subprocess,statistics,hashlib
from pathlib import Path
from rescue.feed import Records
SECONDS=75
units=['readsb','fr24feed','adsb-far-capture','adsb-rescue-shadow','adsb-rescue-feed','adsbexchange-feed']
def snapshot():
 d={}
 for label,path in [('worker','/run/adsb-rescue/status.json'),('feed','/run/adsb-rescue/feed-status.json'),('collector','/run/adsb-far-capture/status.json'),('guard','/run/adsb-async-live-20261109/status.json')]:
  p=Path(path);d[label]=json.loads(p.read_text()) if p.exists() else None
 d['cpu']={u:int(subprocess.check_output(['systemctl','show',u,'-p','CPUUsageNSec','--value'],text=True).strip()) for u in units};d['pids']={u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in units};d['unix']=time.time();return d
before=snapshot();sel=selectors.DefaultSelector();rows={k:[] for k in ['stock','unified']};parsers={k:Records() for k in rows};streams=[]
for k,port in [('stock',30005),('unified',31005)]:
 s=socket.create_connection(('127.0.0.1',port),timeout=3);s.setblocking(False);sel.register(s,selectors.EVENT_READ,k);streams.append(s)
start=time.monotonic()
while time.monotonic()-start<SECONDS:
 for key,_ in sel.select(.1):
  raw=key.fileobj.recv(65536)
  if not raw:raise RuntimeError('Observed socket closed: '+key.data)
  stamp=time.monotonic()
  for wire,f in parsers[key.data].feed(raw):
   if f:rows[key.data].append((stamp,wire,f))
for s in streams:s.close()
after=snapshot();duration=time.monotonic()-start
# Exclude connection/observation edge intervals using original Beast RF ticks.
lo=max(min(f['ticks_12mhz'] for _,_,f in rows[k]) for k in rows)+60000000;hi=min(max(f['ticks_12mhz'] for _,_,f in rows[k]) for k in rows)-60000000
trim={k:[r for r in v if lo<=r[2]['ticks_12mhz']<=hi] for k,v in rows.items()};stock=collections.Counter(w for _,w,f in trim['stock']);unified=collections.Counter(w for _,w,f in trim['unified']);missing=sum((stock-unified).values());extras=[];remaining=stock.copy();arrivals=collections.defaultdict(collections.deque);lat=[]
for stamp,wire,f in trim['stock']:arrivals[wire].append(stamp)
for stamp,wire,f in trim['unified']:
 if remaining[wire]:
  remaining[wire]-=1;lat.append(stamp-arrivals[wire].popleft())
 else:extras.append((stamp,wire,f))
idx=collections.defaultdict(list);duplicates=0;stockoverlap=0
stockindex=collections.defaultdict(list)
for _,_,f in rows['stock']:stockindex[f['message_hex']].append(f['ticks_12mhz'])
for a in stockindex.values():a.sort()
for stamp,wire,f in extras:
 t=f['ticks_12mhz'];p=f['message_hex'];duplicates+=int(any(abs(t-q)<=1440 for q in idx[p]));idx[p].append(t);a=stockindex[p];i=bisect.bisect_left(a,t-1440);stockoverlap+=int(i<len(a) and a[i]<=t+1440)
result=dict(observed_seconds=duration,comparison_edge_seconds_excluded=5,stock_records=sum(stock.values()),stock_missing=missing,unique_extra_records=len(extras),duplicate_extras=duplicates,extras_matching_stock_within_120us=stockoverlap,stock_socket_arrival_delta_median_s=statistics.median(lat),stock_socket_arrival_delta_p95_s=sorted(lat)[int(.95*len(lat))],cpu_core_equivalents={u:(after['cpu'][u]-before['cpu'][u])/1e9/duration for u in units},protected_pids_unchanged=all(before['pids'][u]==after['pids'][u] for u in units),guard=after['guard'],feed_counts_after=after['feed']['counts'],sample_loss_before=before['worker']['health']['local'].get('samples_lost'),sample_loss_after=after['worker']['health']['local'].get('samples_lost'))
assert missing==0 and duplicates==0 and stockoverlap==0,result
assert result['protected_pids_unchanged']
D=Path('/run/adsb-async-live-preflight-20261109');(D/'observation.private.json').write_text(json.dumps(dict(before=before,after=after,results=result),indent=2)+'\n');print(json.dumps(result))

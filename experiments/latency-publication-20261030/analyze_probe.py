import bisect,collections,hashlib,json,statistics,sys
from pathlib import Path
from rescue.wire import BeastParser
from rescue.feed import unwrap
D=Path(sys.argv[1]);O=Path(sys.argv[2]);O.mkdir(parents=True,exist_ok=True)
meta=json.loads((D/'result.json').read_text())
for name,info in meta['files'].items():
 p=D/name;assert p.stat().st_size==info['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==info['sha256']
def read(name):
 parser=BeastParser();raw=(D/(name+'.beast')).read_bytes();rows=[]
 for line in (D/(name+'.chunks.jsonl')).read_text().splitlines():
  c=json.loads(line)
  rows.extend(dict(f,arrival=c['at']) for f in parser.feed(raw[c['offset']:c['offset']+c['bytes']]))
 return rows
stock,combined=read('stock'),read('combined');by=collections.defaultdict(list)
for f in stock:by[(f['ticks_12mhz'],f['message_hex'],f['kind'])].append(f['arrival'])
lo=stock[0]['arrival']+1;hi=stock[-1]['arrival']-4;delays=[];seen=set();extras=0
for f in combined:
 key=(f['ticks_12mhz'],f['message_hex'],f['kind']);ts=by.get(key)
 if ts:
  t=ts.pop(0)
  if lo<=t<=hi:delays.append(f['arrival']-t);seen.add(key)
 elif f['kind']==51:extras+=1
required={ (f['ticks_12mhz'],f['message_hex'],f['kind']) for f in stock if lo<=f['arrival']<=hi }
# Preserve multiplicity as a separate exact core count, not just set membership.
counts=collections.Counter((f['ticks_12mhz'],f['message_hex'],f['kind']) for f in combined)
core=collections.Counter((f['ticks_12mhz'],f['message_hex'],f['kind']) for f in stock if lo<=f['arrival']<=hi)
missing=sum((core-counts).values())
def dist(v):
 v=sorted(v);return dict(count=len(v),min=v[0],median=statistics.median(v),p95=v[min(len(v)-1,int(.95*len(v)))],p99=v[min(len(v)-1,int(.99*len(v)))],max=v[-1]) if v else dict(count=0)
intervals=[b-a for a,b in zip(meta['send_times'],meta['send_times'][1:])];assert meta['before']==meta['after']
summary=dict(protected_health_unchanged=True,probe_seconds=45,stock_records=len(stock),combined_records=len(combined),stock_core_records=sum(core.values()),missing_stock_core_records=missing,measured_existing_relay_delay_seconds=dist(delays),measured_fr24_send_log_interval_seconds=dist(intervals),scope='Read-only current relay measurement, chunk-receipt timing. Unmatched boundaries are not extra recovery claims. FR24 send log cadence is not per-aircraft/backend credit cadence.')
(O/'fresh-probe.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

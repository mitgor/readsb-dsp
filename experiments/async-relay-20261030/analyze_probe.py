import argparse,collections,hashlib,json,statistics
from pathlib import Path
from rescue.wire import BeastParser
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args();D=a.input;meta=json.loads((D/'probe.json').read_text());assert meta['before']==meta['after']
for name,r in meta['files'].items():
 data=(D/name).read_bytes();assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256']
def read(name):
 raw=(D/(name+'.beast')).read_bytes();rows=[];parser=BeastParser()
 for line in (D/(name+'.chunks.jsonl')).read_text().splitlines():
  c=json.loads(line);rows.extend(dict(f,arrival=c['at']) for f in parser.feed(raw[c['offset']:c['offset']+c['bytes']]))
 return rows
stock=read('stock');test=read('asynchronous');key=lambda f:(f['ticks_12mhz'],f['message_hex'],f['kind']);lo=stock[0]['arrival']+1;hi=stock[-1]['arrival']-1;core=collections.Counter(key(f) for f in stock if lo<=f['arrival']<=hi);actual=collections.Counter(key(f) for f in test);missing=sum((core-actual).values());by=collections.defaultdict(collections.deque)
for f in test:by[key(f)].append(f['arrival'])
delay=[]
for f in stock:
 if lo<=f['arrival']<=hi and by[key(f)]:delay.append(by[key(f)].popleft()-f['arrival'])
delay.sort();dist=dict(count=len(delay),min=delay[0],median=statistics.median(delay),p95=delay[int(.95*len(delay))],p99=delay[int(.99*len(delay))],max=delay[-1]);final=json.loads((D/'runtime/final.json').read_text());assert not missing and final['forwarded_to_fr24'] is False;assert final['relay_counts'].get('dsp_frames_relayed',0)==0
report=dict(stock_core_records=sum(core.values()),missing_stock_core_records=missing,delay_seconds=dist,process_cpu_s=meta['cpu_s'],wall_s=meta['wall_s'],equivalent_one_core_percent=100*meta['cpu_s']/meta['wall_s'],peak_rss_kib=meta['peak_rss_kib'],dedup_history_entries=final['history_entries'],cache_capacity_evictions=final['dedup'].get('capacity_evictions',0),protected_health_unchanged=True,real_dsp_forwarded=0,fr24_attached=False,scope=meta['scope'],limits='Arrival-time difference between independent localhost clients, not RF-to-cloud latency. Slight negative deltas are possible from socket scheduling. No live DSP producer was connected, so this cannot measure real-extra retention or complete-pipeline accuracy.')
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

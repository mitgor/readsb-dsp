#!/usr/bin/env python3
import collections,json,statistics,hashlib,html,subprocess,urllib.request
from pathlib import Path
from rescue.wire import BeastParser
R=Path(__file__).resolve().parents[2];D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/async-check-20261109/files/data');OUT=R/'validation/async-check-20261109';OUT.mkdir(parents=True,exist_ok=True)
m=json.loads((D/'probe.json').read_text());assert m['before']==m['after']
def read(name):
 b=(D/(name+'.beast')).read_bytes();rows=[];p=BeastParser()
 for line in (D/(name+'.chunks.jsonl')).read_text().splitlines():
  c=json.loads(line);rows.extend({**v,'arrival':c['at']} for v in p.feed(b[c['offset']:c['offset']+c['bytes']]))
 return rows
stock=read('stock');streams={n:read(n) for n in ['asynchronous','production']};key=lambda f:(f['kind'],f['ticks_12mhz'],f['message_hex']);lo=stock[0]['arrival']+2;hi=stock[-1]['arrival']-5;core=[f for f in stock if lo<=f['arrival']<=hi];counts=collections.Counter(key(f) for f in core);result={}
for name,rows in streams.items():
 index=collections.defaultdict(collections.deque)
 for row in rows:index[key(row)].append(row['arrival'])
 missing=sum((counts-collections.Counter(key(f) for f in rows)).values());assert missing==0
 delay=[]
 for f in core:
  if index[key(f)]:delay.append(index[key(f)].popleft()-f['arrival'])
 delay.sort();result[name]=dict(core_records=len(core),missing_core_records=missing,arrival_delay_s=dict(min=min(delay),median=statistics.median(delay),p95=delay[int(.95*len(delay))],p99=delay[int(.99*len(delay))],max=max(delay)))
final=json.loads((D/'runtime/final.json').read_text());assert final['forwarded_to_fr24'] is False and final['relay_counts'].get('dsp_frames_relayed',0)==0
summary=dict(previous_discussion='2026-10-30',production_changed=False,producer_integration_complete=False,real_dsp_extras_tested=False,fr24_or_adsbx_attached=False,tests_mac=9,tests_pi=9,history_s=5,async_stock_holdback_s=0,production_holdback_s=3,comparison=result,protected_health_unchanged=True,probe_cpu_s=m['cpu_s'],wall_s=m['wall_s'],equivalent_one_core_percent=100*m['cpu_s']/m['wall_s'],peak_rss_kib=m['peak_rss_kib'],cache_entries=final['history_entries'],cache_capacity_evictions=final['dedup'].get('capacity_evictions',0),first_attempt='Failed: owned /dev/shm tree disappeared before final write; no usable capture retained. Cause unconfirmed; not counted as validation.',retry='Successful isolated /run tmpfs probe; 45s capture, no production config changes.',limitations=['Stock-only async test: no real DSP producer attached, no full-current-pipeline extras-retention proof.','Arrival deltas between independent local TCP clients, not RF-to-cloud latency; small negative values can occur from scheduling.','Test CPU/RSS includes imports, three socket recordings, history, status and health checks, not just dedup.','Existing prototype250ms extra age gate can reject valid slow results from current production; it is not a universal FR24 limit.','Production producer admission/epoch mapping and full-enabled-pipeline RF parity remain required.','Stock-first cannot retract an already-sent extra if stock arrives later; race is counted.'])
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
a=result['asynchronous']['arrival_delay_s'];p=result['production']['arrival_delay_s']
md=f'''# Asynchronous output review — 9 November 2026

We discussed this on30 October and built a separate test relay, not a production deployment. Current production still uses its3-second global timestamp holdback.

The prototype immediately queues stock and accepts independent validated source queues. A shared5-second bounded dedup cache covers all sources. It matches payload plus RF transmission timestamp and receiver epoch, preserving legitimate later repeats. Five seconds is memory retention, not a wait. Per-source-only caches would leave duplicates between DSP methods.

Nine tests pass on both Mac and Pi, including slow/absent producers, cross-stream duplicates, repeated payloads at distinct RF times, bounded history, forbidden/disabled sources and isolated clients. A new finite Pi probe used a read-only stock client, isolated loopback output and a separate production-output observer: no SDR/mirror consumer, configuration/model/gain changes, or feeder route change. Nice19, core3,35% quota,256MiB and120s maximum bound the owned process.

| Output | Matching core stock records | Missing | Median arrival delay | P95 | P99 |
|---|---:|---:|---:|---:|---:|
| Isolated async stock | {len(core):,} | 0 | {a['median']*1000:.3f}ms | {a['p95']*1000:.3f}ms | {a['p99']*1000:.3f}ms |
| Current production | {len(core):,} | 0 | {p['median']*1000:.3f}ms | {p['p95']*1000:.3f}ms | {p['p99']*1000:.3f}ms |

These are local arrival differences, not RF-to-FR24 latency. Protected process IDs, method/config hashes, gain and stock sample-loss counters remained unchanged; FR24 stayed connected at health checks. The prototype's45-second recording/50-second runtime consumed{m['cpu_s']:.3f} CPU seconds ({100*m['cpu_s']/m['wall_s']:.2f}% of one core), including recording/import/status overhead. Peak RSS{m['peak_rss_kib']/1024:.1f}MiB. No cache-capacity evictions.

**No live DSP producers were attached to the asynchronous output.** Consequently these results prove stock transport behavior and synthetic queue/dedup behavior, not complete-pipeline DSP recovery or FR24 cloud acceptance. Current all-method configuration (except header) stayed active in production.

The remaining work is to connect per-completion producers through causal CRC/address/conflict/alignment admission with the genuine radio epoch, then compare retained/lost extras and timing against the full current enabled pipeline on identical fresh RF. The old250ms candidate-age gate must not be mistaken for a universal FR24 rule; current valid methods can take longer. Preserve original transmission timestamps and audit late-stock-after-extra races. Closely coupled C/Rust stages can reuse computation while publishing completed results; do not duplicate their frontend just to claim independence.

The first probe's /dev/shm tree disappeared during execution and no usable capture remains; cause unconfirmed. Its journal is preserved as a failed attempt. The retry used a new isolated /run RAM directory and succeeded. Checksum-verified raw transport evidence and code snapshots are private. Production routing is unchanged.
'''
(OUT/'report.md').write_text(md);(OUT/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Asynchronous relay check</title><style>body{font:17px/1.5 system-ui;max-width:1100px;margin:35px auto;padding:20px;background:#101b29;color:#e2ebf4}pre{font:inherit;white-space:pre-wrap}</style><pre>'+html.escape(md)+'</pre>')
remote='/usr/share/adsb-rescue/async-check-20261109';subprocess.run(['ssh','adsb-rpi','sudo','mkdir','-p',remote],check=True);publication={}
for name in ['summary.json','report.html']:
 b=(OUT/name).read_bytes();h=hashlib.sha256(b).hexdigest();subprocess.run(['ssh','adsb-rpi','sudo','tee',remote+'/'+name],input=b,stdout=subprocess.DEVNULL,check=True);assert hashlib.sha256(urllib.request.urlopen('http://192.168.2.195/neural-rescue/async-check-20261109/'+name,timeout=10).read()).hexdigest()==h;publication[name]=h
(OUT/'publication.json').write_text(json.dumps(publication,indent=2)+'\n');print(json.dumps(summary,indent=2))

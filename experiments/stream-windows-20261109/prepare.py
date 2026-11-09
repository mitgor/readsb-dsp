"""Frozen selection by captured stock/range, never candidate results."""
import json,hashlib,collections,bisect,subprocess,os
from pathlib import Path
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/stream-windows-20261109';W=R/'data/transfer/stream-windows-20261109';O.mkdir(exist_ok=False);W.mkdir(exist_ok=False);(W/'rf').mkdir()
source=R/'data/transfer/retrain-companion-20261029/prepared';positions=json.loads((source/'positions.json').read_text());by=collections.defaultdict(list)
for p in positions:
 if p['quality']:by[p['icao']].append(p)
for v in by.values():v.sort(key=lambda p:p['available'])
def dist(r,unix):
 pp=[p for p in by[r['message_hex'][2:8]] if p['available']<=unix and 0<=unix-p['position_time']<=15];return max(pp,key=lambda p:p['available'])['distance_nm'] if pp else None
choices=[];cache={}
for c in json.loads((source/'cases.json').read_text()):
 if not c['streams_complete'] or not c['alignment']['verified']:continue
 if c['reference_file'] not in cache:cache[c['reference_file']]=json.loads((source/c['reference_file']).read_text())
 refs=cache[c['reference_file']]
 for offset in range(0,c['sample_count']-2401200+1,2400000):
  first=c['sample_start']+offset;lo=(first+600)*5;hi=lo+12000000;stock=[r for r in refs['stock'] if lo<=r['ticks']<hi]
  for r in stock:r['distance_nm']=dist(r,c['unix']+(r['ticks']-c['sample_start']*5)/12000000)
  choices.append(dict(case=c,offset=offset,first=first,stock=stock,far=sum((r['distance_nm'] or 0)>=180 for r in stock)))
# Engineering set: distant opportunities first; controls selected independently.
far=sorted([c for c in choices if c['far']>0],key=lambda c:(-c['far'],c['first']))[:16];near=sorted([c for c in choices if not c['far']],key=lambda c:(-len(c['stock']),c['first']))[:8];selected=far+near;assert selected
rows=[];reference_stock={};actual={}
for i,v in enumerate(selected):
 c=v['case'];raw=(source/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256'];raw=raw[v['offset']*2:(v['offset']+2401200)*2];name=f'window-{i:03d}.uc8';(W/'rf'/name).write_bytes(raw);lo=(v['first']+600)*5;hi=lo+12000000;refs=cache[c['reference_file']]
 ss=[dict(r) for r in refs['stock'] if lo-360000000<=r['ticks']<=hi+12000000]
 for r in ss:r['distance_nm']=dist(r,c['unix']+(r['ticks']-c['sample_start']*5)/12000000)
 aa=[r for r in refs['actual'] if lo<=r['ticks']<hi]
 rows.append(dict(file=name,sha256=hashlib.sha256(raw).hexdigest(),epoch=c['epoch'],first=v['first'],wall=c['unix']+v['offset']/2400000,stock=ss,actual=aa,far_stock=v['far'],origin_file=c['file'],origin_sha256=c['sha256'],raw_sample_offset=v['offset'],rf_seconds=1))
protocol=dict(schema='stream-window-experiment-v1',created_unix=__import__('time').time(),core_ms=[1000,500,250,100],halo_samples=600,rolling_history_rf_s=1,minimum_stream_matches=10,max_stream_mad_ticks=360,final_admission_min_energy_matches=20,final_admission_max_median_us=2,duplicate_tolerance_ticks=1440,stock_only_prior_and_conflict_guards=True,no_threshold_tuning=True,scope='Consumed historical engineering RF, selection by recorded distant stock only. Not new prospective evidence. Causal quality-gated stock range; not independent physical truth.',rows=rows)
(W/'dataset.private.json').write_text(json.dumps(protocol)+'\n');(O/'selection.json').write_text(json.dumps(dict(windows=len(rows),far_selected=len(far),near_controls=len(near),stock=sum(len(v['stock']) for v in selected),far_stock=sum(v['far'] for v in selected),source_manifest_sha256=hashlib.sha256((source/'cases.json').read_bytes()).hexdigest(),dataset_sha256=hashlib.sha256((W/'dataset.private.json').read_bytes()).hexdigest()),indent=2)+'\n')
# Explicit new reservation provenance, in addition to existing evaluation reservations.
p=R/'data/raw/long-validation-stream-windows-20261109';p.mkdir(exist_ok=False);(p/'reserved-intervals.json').write_text(json.dumps(dict(schema='long-validation-v1',evaluation_only=True,captures=[dict(epoch=r['epoch'],sample_start=r['first'],sample_count=2401200) for r in rows]),indent=2)+'\n')
print((O/'selection.json').read_text())

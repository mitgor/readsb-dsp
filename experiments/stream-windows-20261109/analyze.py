"""Full enabled current union and actual-output masks, by causal stock range."""
import argparse,json,collections,bisect,statistics,hashlib
from pathlib import Path
from rescue.shadow import evaluate
from rescue.stock_history import StockHistory
from bench_stream import quantile
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');W=R/'data/transfer/stream-windows-20261109';O=R/'results/stream-windows-20261109'
p=argparse.ArgumentParser();p.add_argument('--stream',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();data=json.loads((W/'dataset.private.json').read_text());ss=json.loads(a.stream.read_text());bb=json.loads(a.baseline.read_text());assert len(data['rows'])==len(ss['results'])==len(bb['cases']);pos=json.loads((R/'data/transfer/retrain-companion-20261029/prepared/positions.json').read_text())
def match(r,rows):return any(v['message_hex']==r['message_hex'] and abs(v['ticks']-r['ticks'])<=1440 for v in rows)
def difference(left,right):return [r for r in left if not match(r,right)]
range_index={};range_cache={}
def distance(r,c):
 key=(c['file'],r['message_hex'],r['ticks'])
 if key in range_cache:return range_cache[key]
 if c['file'] not in range_index:
  index=collections.defaultdict(list)
  for p in c.get('positions') or pos:
   if p.get('quality',True) is True:index[p['icao']].append((p.get('available_unix',p.get('available')),p.get('position_unix',p.get('position_time')),p['distance_nm']))
  for v in index.values():v.sort()
  range_index[c['file']]=index
 t=c['wall']+(r['ticks']-c['first']*5)/12000000;v=range_index[c['file']][r['message_hex'][2:8]];i=bisect.bisect_right(v,(t,float('inf'),float('inf')));answer=None
 for available,stamp,d in reversed(v[:i]):
  if available<t-15:break
  if 0<=t-stamp<=15:answer=d;break
 range_cache[key]=answer;return answer
def band(d):return 'unknown' if d is None else '0-180' if d<180 else '180-200' if d<200 else '200-250' if d<250 else '250+'
results={};excluded=[];percase=[]
for c,s,b in zip(data['rows'],ss['results'],bb['cases']):
 assert c['file']==s['file']==b['file'];history=StockHistory()
 for r in c['stock']:history.append(r)
 frames=history.snapshot();lo=(c['first']+600)*5;hi=lo+12000000
 variants={v['core_ms']:v for v in s['variants']};base_stream=variants[1000]['strict'];base,audit,_=evaluate(frames,b['candidates']+base_stream,lo,hi)
 if not audit['verified']:excluded.append(dict(file=c['file'],audit=audit));continue
 baseids=[r for r in base if r['source']=='stream1090'];stock=[r for r in c['stock'] if lo<=r['ticks']<hi]
 detail=dict(file=c['file'],baseline_total=len(base),baseline_stream_only=len(baseids),baseline_far=sum((distance(r,c) or 0)>=180 for r in base),variants={})
 for ms,v in variants.items():
  for policy in ['strict','rolling']:
   key=f'{ms}-{policy}';rows,check,_=evaluate(frames,b['candidates']+v[policy],lo,hi);assert check['verified'];lost=difference(base,rows);added=difference(rows,base);novel=difference(added,c['actual']+c.get('accepted_historical',[]));streamonly=[r for r in rows if r['source']=='stream1090'];lat=[];paired=[]
   for r in streamonly:
    vv=[x for x in v[policy] if match(r,[x])]
    if vv:
     latency=min(x['ready_age_s'] for x in vv);lat.append(latency);old=[x for x in base_stream if match(r,[x])]
     if old and match(r,baseids):paired.append(min(x['ready_age_s'] for x in old)-latency)
   if key not in results:results[key]=dict(core_ms=ms,calibration=policy,windows=0,full_pipeline_extras=0,stream_incremental_extras=0,baseline_stream_incremental_extras=0,lost_full_pipeline=0,added_vs_current=0,novel_vs_current_and_actual=0,bins=collections.defaultdict(collections.Counter),latency=[],paired_saved=[],child_cpu_s=0.,coordinator_cpu_s=0.,failed_clips=0,invocations=0,stock_opportunities=0,far_stock_opportunities=0,far_stock_aircraft=set(),far_stream_aircraft=set())
   z=results[key];z['windows']+=1;z['full_pipeline_extras']+=len(rows);z['stream_incremental_extras']+=len(streamonly);z['baseline_stream_incremental_extras']+=len(baseids);z['lost_full_pipeline']+=len(lost);z['added_vs_current']+=len(added);z['novel_vs_current_and_actual']+=len(novel);z['latency']+=lat;z['paired_saved']+=paired;z['child_cpu_s']+=v['child_cpu_s'];z['coordinator_cpu_s']+=v['coordinator_cpu_s'];z['failed_clips']+=v['failure_counts'].get(policy+'_unaligned_clips',0);z['invocations']+=v['invocations'];z['stock_opportunities']+=len(stock)
   for r in stock:
    if (distance(r,c) or 0)>=180:z['far_stock_opportunities']+=1;z['far_stock_aircraft'].add(r['message_hex'][2:8])
   for label,rr in [('stock',stock),('baseline_full',base),('full',rows),('stream_only',streamonly),('lost',lost),('added',added),('novel',novel)]:
    for r in rr:
     d=distance(r,c);z['bins'][band(d)][label]+=1
     if label=='stream_only' and d is not None and d>=180:z['far_stream_aircraft'].add(r['message_hex'][2:8])
   detail['variants'][key]=dict(full=len(rows),stream_only=len(streamonly),lost=len(lost),added=len(added))
 percase.append(detail)
for z in results.values():
 z['candidate_ready_latency']=quantile(z.pop('latency'));z['matched_packet_latency_saved']=quantile(z.pop('paired_saved'));z['child_cpu_per_rf_s']=z['child_cpu_s']/z['windows'];z['far_stock_aircraft']=len(z['far_stock_aircraft']);z['far_stream_aircraft']=len(z['far_stream_aircraft'])
ref=results['1000-strict']['child_cpu_per_rf_s']
for z in results.values():z['child_cpu_change_percent']=100*(z['child_cpu_per_rf_s']/ref-1)
allcost={ms:sum(v['child_cpu_s'] for c in ss['results'] for v in c['variants'] if v['core_ms']==ms) for ms in [1000,500,250,100]}
all_rf=len(data['rows']);worker=bb['worker_cpu_s'];cost_summary={str(ms):dict(stream_child_cpu_s=cpu,stream_child_cpu_per_rf_s=cpu/all_rf,stream_cpu_change_percent=100*(cpu/allcost[1000]-1),decoder_kernel_bundle_cpu_per_rf_s=(worker+cpu)/all_rf,decoder_kernel_bundle_cpu_change_percent=100*((worker+cpu)/(worker+allcost[1000])-1)) for ms,cpu in allcost.items()}
out=dict(cost_all_RF=cost_summary,valid_rf_seconds=len(percase),excluded=excluded,variants=results,per_case=percase,stream_sha256=ss['binary_sha256'],baseline_worker_cpu_s=bb['worker_cpu_s'],latency_scope=ss['latency_scope'],native_clock=ss['native_RF_clock'],notes=['Historical consumed evaluation RF, not prospective range evidence.','Current complete enabled native/Rust/neural/pulse/sequence/acquisition union recomputed on copied target workers. SIC/header off; Broad CRC quarantined.','Stock and historical actual-unified records mask discoveries; accepted historical ledger exists for v4 subset only.','Candidate-ready latency covers Stream computation/calibration, not final admission/transport/cloud; stock arrival times are not saved.','Core/halo seams owned once, CRC/prior-stock/conflict/alignment guards retained. Rolling offset minimum10/MAD360, 1s memory; final energy alignment20/2us unchanged.'])
a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:{x:v[x] for x in ['stream_incremental_extras','lost_full_pipeline','added_vs_current','novel_vs_current_and_actual','child_cpu_change_percent','candidate_ready_latency','bins']} for k,v in results.items()},indent=2))

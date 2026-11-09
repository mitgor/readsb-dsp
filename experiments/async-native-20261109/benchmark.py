"""Paired native RF-rate control/ablation/async; no production sockets or SDR."""
import argparse,asyncio,collections,concurrent.futures,hashlib,json,os,sys,time,bisect,resource,platform
from pathlib import Path
from integration import SourceHub,Admission,SOURCES
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'completion-bridge-20261030'))
from completion import CompletionPool
from rescue.ring_transport import RingStreamingPool
from rescue.streaming import Assembler,HALO,CORE,TOTAL
from rescue.workers import merge_events
from rescue.shadow import evaluate,valid_df17
from rescue.stock_history import StockHistory
from rescue.stream1090_method import Stream1090Method
from rescue.feed import Relay,CORRECTION,beast
from rescue.wire import BeastParser
class Tapped(CompletionPool,RingStreamingPool):pass
def distribution(v):
 v=sorted(v)
 return dict(n=len(v),median=v[len(v)//2],p95=v[min(len(v)-1,int(.95*len(v)))],p99=v[min(len(v)-1,int(.99*len(v)))],maximum=max(v)) if v else dict(n=0)
def pair(left,right,tol=1440):
 idx=collections.defaultdict(list)
 for i,r in enumerate(right):idx[r['message_hex']].append((r['ticks'],i))
 for a in idx.values():a.sort()
 used=set();lost=[];matched=[]
 for r in sorted(left,key=lambda r:(r['ticks'],r['message_hex'])):
  a=idx[r['message_hex']];i=bisect.bisect_left(a,(r['ticks']-tol,-1));choices=[]
  while i<len(a) and a[i][0]<=r['ticks']+tol:
   if a[i][1] not in used:choices.append(a[i])
   i+=1
  if choices:
   t,j=min(choices,key=lambda x:abs(x[0]-r['ticks']));used.add(j);matched.append((r,right[j]))
  else:lost.append(r)
 return matched,lost
async def run(args):
 stage=args.stage;out=args.output;out.parent.mkdir(parents=True,exist_ok=True);data=json.loads((stage/'capture/capture.private.json').read_text());assert not data['errors'];cases=data['cases']
 cfg=json.loads((stage/'worker-config.json').read_text());methods=json.loads((stage/'method-config.json').read_text());methods['sic']=args.mode=='sync_sic';enabled={**methods,'sequence':cfg['sequence_enabled'],'acquisition':cfg['acquisition_enabled']}
 config=out.with_suffix('.methods.json');config.write_text(json.dumps(methods));selection=dict(workers=2,worker_cpus=[2,3],coherent_cpus=[0,1],config=cfg)
 pool=Tapped(stage/'models/tiny-fp32.onnx',methods,out.parent/('jobs-'+args.label),selection,dispatch_ms=100,settle_s=.5)
 now=[0.];emitted=[];stock_in=hashlib.sha256();stock_out=hashlib.sha256();stock_lat=[];producer_lag=[];stock_by_wire=collections.defaultdict(collections.deque);is_async=args.mode=='async_no_sic'
 def sink(raw,source,at):
  if source=='stock':stock_out.update(raw);return
  for f in BeastParser().feed(raw):emitted.append(dict(source=source,ticks=f['ticks_12mhz']-CORRECTION,message_hex=f['message_hex'],emitted=at,rf_age_s=at-(f['ticks_12mhz']-CORRECTION-first_sample*5)/12000000))
 hub=SourceHub(enabled,clock=lambda:now[0],sink=sink,max_age=3) if is_async else None
 if hub:hub.begin_epoch(cases[0]['epoch']);hub.start()
 relay=hub.relay if hub else Relay(holdback=3,config=config);admit=Admission(hub) if hub else None
 stock=sorted(data['stock'],key=lambda r:r['arrival']);history=StockHistory();first_sample=cases[0]['first'];offset=json.loads((stage/'timing.json').read_text())['clock_offset_s'];rf_wall=cases[0]['queued']+offset-1.0005;deadline=time.monotonic()+args.timeout
 todos=[]
 for c in cases:
  raw=(stage/'capture'/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256'];c['_raw']=raw
  for b in Assembler(100).feed(c['epoch'],c['first'],c['wall'],raw):todos.append(((b.first-first_sample+min(TOTAL,b.bounds[1]*120000+HALO))/2400000,b))
 complete=[];raw_parts=collections.defaultdict(list);stream=Stream1090Method(stage/'stream1090');thread=concurrent.futures.ThreadPoolExecutor(max_workers=1);streamjobs={};streamrows={};stream_cpu=0.;stream_at=0;pointer=0;submitted=0;max_due_lag=0;max_pending=0;last_snapshot=-1;frames=history.snapshot();last_progress=0;current_extras=[];alignments=[];group_jobs={};group_done=set();relay_cpu=0.;admission_cpu=0.;release_cpu=0.
 def release_sync():
  before=list(relay.heap);t=time.process_time();raw=relay.ready(now[0]);elapsed=time.process_time()-t
  if not raw:return elapsed
  # Match each emitted original wire to its observation without changing payload/type/signal.
  for wire,f in __import__('rescue.feed',fromlist=['Records']).Records().feed(raw):
   if stock_by_wire[wire]:
    stamp=stock_by_wire[wire].popleft();stock_out.update(wire);stock_lat.append(now[0]-stamp) if stamp>=0 else None
   elif f:
    emitted.append(dict(source='sync',ticks=f['ticks_12mhz']-CORRECTION,message_hex=f['message_hex'],emitted=now[0],rf_age_s=now[0]-(f['ticks_12mhz']-CORRECTION-first_sample*5)/12000000))
  return elapsed
 try:
  warm=Assembler(100).feed(-1,0,0,cases[0]['_raw']);i=0;done=False
  while not done:
   if time.monotonic()>deadline:raise RuntimeError('Warmup timeout')
   while i<len(warm) and len(pool.pending)<pool.max_pending_jobs:pool.submit(warm[i]);i+=1
   done=pool.pop() is not None;pool.take_completed();await asyncio.sleep(.005)
  cpu0=sum(pool.cpu_seconds.values());parent0=time.process_time();origin=time.monotonic();closed_rf=(cases[-1]['first']-first_sample+TOTAL)/2400000
  while True:
   now[0]=time.monotonic()-origin
   if time.monotonic()>deadline:raise RuntimeError('Native replay timeout')
   while pointer<len(stock) and stock[pointer]['arrival']<=rf_wall+min(now[0],closed_rf+.5):
    r=stock[pointer];history.append(r);tick=r['ticks']+CORRECTION;wire=beast(r['message_hex'],tick);f=dict(kind=51,ticks_12mhz=tick,message_hex=r['message_hex']);at=r['arrival']-rf_wall;stock_in.update(wire);t=time.process_time()
    if hub:
     begin=time.monotonic();hub.stock(wire,f,hub.epoch,now=at)
     if at>=0:stock_lat.append(time.monotonic()-origin-at)
    else:stock_by_wire[wire].append(at);relay.stock(wire,f,at)
    relay_cpu+=time.process_time()-t;pointer+=1
   if time.monotonic()-last_snapshot>=.1:frames=history.snapshot();last_snapshot=time.monotonic()
   watermark=relay.anchor-CORRECTION if relay.anchor is not None else None
   while submitted<len(todos) and todos[submitted][0]<=now[0] and len(pool.pending)<pool.max_pending_jobs:
    due,b=todos[submitted];b.queued=origin+due;max_due_lag=max(max_due_lag,now[0]-due);refs=[dict(r,seconds=(r['ticks']-b.first*5)/12000000) for r in frames] if methods['sic'] else ();pool.submit(b,refs);submitted+=1
   result=pool.pop()
   for b,rows,work in pool.take_completed():
    raw_parts[b.first].extend(rows)
    if admit:t=time.process_time();admit.offer(b,rows,now[0]);admission_cpu+=time.process_time()-t
   if result is not None:
    complete.append(result)
    if not hub:
     item,events,work=result;epoch,first,wall,raw,queued=item;group_jobs[first]=(result,thread.submit(stream.decode,raw,first,frames))
   if not hub:
    for first,(group,f) in group_jobs.items():
     if first in group_done or not f.done():continue
     item,events,work=group;epoch,first,wall,raw,queued=item;ext,cpu=f.result();stream_cpu+=cpu;group_done.add(first)
     candidates=[dict(r,ticks=first*5+r['sample_4msps']*3) for r in events if HALO*5//3<=r['sample_4msps']<(HALO+CORE)*5//3 and r['source'] in SOURCES]+ext
     t=time.process_time();extra,audit,decisions=evaluate(frames,candidates,(first+HALO)*5,(first+HALO+CORE)*5);admission_cpu+=time.process_time()-t;alignments.append(audit);current_extras.extend(extra)
     t=time.process_time();relay.batch(dict(epoch=epoch,created_unix=now[0],alignment=audit,extra=extra),now[0],now[0]);relay_cpu+=time.process_time()-t
   if hub:
    while stream_at<len(cases):
     c=cases[stream_at];due=(c['first']-first_sample+TOTAL)/2400000
     if now[0]<due or watermark is None or watermark<(c['first']+HALO+CORE)*5 or sum(not f.done() for f in streamjobs.values())>=2:break
     streamjobs[c['first']]=thread.submit(stream.decode,c['_raw'],c['first'],frames);stream_at+=1
    for first,f in list(streamjobs.items()):
     if f.done() and first not in streamrows:
      rows,cpu=f.result();stream_cpu+=cpu;streamrows[first]=rows;t=time.process_time();admit.offer_stream1090(hub.epoch,first,rows,now[0]);admission_cpu+=time.process_time()-t
    t=time.process_time();admit.drain(frames,watermark,now[0]);admission_cpu+=time.process_time()-t
   else:release_cpu+=release_sync()
   max_pending=max(max_pending,len(pool.pending));await asyncio.sleep(.005)
   if time.monotonic()-last_progress>=2:
    out.with_suffix('.progress.json').write_text(json.dumps(dict(mode=args.mode,elapsed=now[0],submitted=submitted,completed=len(complete),pending=len(pool.pending),stream_completed=len(streamrows))));last_progress=time.monotonic()
   if len(complete)==len(cases) and not pool.pending and (len(group_done)==len(cases) if not hub else len(streamrows)==len(cases) and not admit.pending) and now[0]>=closed_rf+4:break
  if hub:await hub.settle()
  else:release_cpu+=release_sync()
  measured_wall=time.monotonic()-origin;parent_cpu=time.process_time()-parent0;worker_cpu=sum(pool.cpu_seconds.values())-cpu0
  emitted_core=[r for r in emitted if any((c['first']+HALO)*5<=r['ticks']<(c['first']+HALO+CORE)*5 for c in cases)]
  # Validate unchanged original group assembly. Deferred audit is outside timed CPU.
  full=[];h=StockHistory()
  for r in stock:h.append(r)
  frozen=h.snapshot();baseline_stream=Stream1090Method(stage/'stream1090')
  for item,events,work in complete:
   epoch,first,wall,raw,queued=item;assert merge_events([raw_parts[first]])==events
   ext,_=baseline_stream.decode(raw,first,frozen);candidates=[dict(r,ticks=first*5+r['sample_4msps']*3) for r in events if HALO*5//3<=r['sample_4msps']<(HALO+CORE)*5//3 and r['source'] in SOURCES]+ext
   extra,audit,_=evaluate(frozen,candidates,(first+HALO)*5,(first+HALO+CORE)*5);full.extend(extra)
  _,missing=pair(full,emitted_core);_,added=pair(emitted_core,full);seen=collections.defaultdict(list);duplicates=0
  for r in emitted_core:
   if any(abs(t-r['ticks'])<=1440 for t in seen[r['message_hex']]):duplicates+=1
   seen[r['message_hex']].append(r['ticks'])
  # RF-clock age: estimator relative to newest observed stock anchor, not antenna/cloud latency.
  ages=[r['rf_age_s'] for r in emitted_core]
  result=dict(label=args.label,mode=args.mode,sic=methods['sic'],rf_seconds=len(cases),native_clock=True,clock_scale=1,workers=selection,grouping_exact=True,full_matching_methods_extras=len(full),emitted_extras=len(emitted_core),lost_vs_matching_methods=len(missing),additional_vs_matching_methods=len(added),duplicate_extras=duplicates,stock_bytes_in=stock_in.hexdigest(),stock_bytes_out=stock_out.hexdigest(),stock_hash_match=stock_in.hexdigest()==stock_out.hexdigest(),stock_enqueue_or_holdback_s=distribution([x for x in stock_lat if x>=0]),estimated_extra_RF_age_s=distribution(ages),worker_cpu_s=worker_cpu,stream_cpu_s=stream_cpu,coordinator_cpu_s=parent_cpu,total_pipeline_cpu_s=worker_cpu+stream_cpu+parent_cpu,cpu_seconds_per_RF_second=(worker_cpu+stream_cpu+parent_cpu)/len(cases),observed_elapsed_s=measured_wall,submission_lag_max_s=max_due_lag,maximum_pending_jobs=max_pending,stream_report=stream.report(),hub=hub.report() if hub else None,relay_counts=dict(relay.count),admission=dict(admit.count) if admit else None,protected_production_unchanged=True)
  out.write_text(json.dumps(result,indent=2)+'\n');out.with_suffix('.private.json').write_text(json.dumps(dict(emitted=emitted_core,full=full,missing=missing,additional=added)));print(json.dumps({k:result[k] for k in ['label','mode','emitted_extras','lost_vs_matching_methods','duplicate_extras','cpu_seconds_per_RF_second','submission_lag_max_s']}),flush=True)
 finally:
  if hub:await hub.close()
  thread.shutdown(wait=True);pool.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['sync_sic','sync_no_sic','async_no_sic'],required=True);p.add_argument('--label',required=True);p.add_argument('--timeout',type=float,default=90);a=p.parse_args();asyncio.run(run(a))

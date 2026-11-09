"""All current algorithms, independent completion/Stream1090 producers, isolated output."""
import argparse,asyncio,collections,concurrent.futures,hashlib,json,os,sys,time,bisect,platform
from pathlib import Path
from integration import SourceHub,Admission,SOURCES
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'completion-bridge-20261030'))
from bridge import CompletionPool
from rescue.ring_transport import RingStreamingPool
from rescue.streaming import Assembler,HALO,CORE,TOTAL
from rescue.workers import merge_events
from rescue.shadow import evaluate,valid_df17
from rescue.stock_history import StockHistory
from rescue.stream1090_method import Stream1090Method
from rescue.feed import CORRECTION,beast
from rescue.wire import BeastParser
class Tapped(CompletionPool,RingStreamingPool):pass
def pair(left,right,tol=1440):
 index=collections.defaultdict(list)
 for i,r in enumerate(right):index[r['message_hex']].append((r['ticks'],i))
 for v in index.values():v.sort()
 used=set();missing=[];matched=[]
 for r in sorted(left,key=lambda x:(x['ticks'],x['message_hex'])):
  v=index[r['message_hex']];at=bisect.bisect_left(v,(r['ticks']-tol,-1));candidates=[]
  while at<len(v) and v[at][0]<=r['ticks']+tol:
   if v[at][1] not in used:candidates.append(v[at])
   at+=1
  if candidates:
   t,i=min(candidates,key=lambda x:abs(x[0]-r['ticks']));used.add(i);matched.append((r,right[i]))
  else:missing.append(r)
 return matched,missing
async def main(args):
 stage=args.stage;out=args.output;out.parent.mkdir(parents=True,exist_ok=True);data=json.loads((stage/'capture/capture.private.json').read_text());assert not data['errors'];cases=data['cases'];assert len({c['epoch'] for c in cases})==1
 cfg=json.loads((stage/'worker-config.json').read_text());methods=json.loads((stage/'method-config.json').read_text());enabled={**methods,'sequence':cfg['sequence_enabled'],'acquisition':cfg['acquisition_enabled']}
 selection=dict(workers=1,worker_cpus=[3] if sys.platform=='linux' else [],coherent_cpus=[3] if sys.platform=='linux' else [None],config=cfg)
 pool=Tapped(stage/'models/tiny-fp32.onnx',methods,args.job_runtime or stage/('jobs-'+args.label),selection,dispatch_ms=100,settle_s=.5)
 deadline=time.monotonic()+args.timeout;complete=[];raw_parts=collections.defaultdict(list);stock=sorted(data['stock'],key=lambda r:r['arrival']);first_sample=cases[0]['first'];rf_wall=cases[0]['queued']+json.loads((stage/'timing.json').read_text())['clock_offset_s']-1.0005
 todos=[]
 for c in cases:
  raw=(stage/'capture'/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256'];c['_raw']=raw
  batches=Assembler(100).feed(c['epoch'],c['first'],c['wall'],raw);assert len(batches)==10
  for b in batches:
   end=min(TOTAL,b.bounds[1]*120000+HALO);todos.append(((b.first-first_sample+end)/2400000,b))
 now=[0.];emitted=[];stock_bytes=0
 def sink(raw,source,at):
  nonlocal stock_bytes
  if source=='stock':stock_bytes+=len(raw);return
  for f in BeastParser().feed(raw):emitted.append(dict(source=source,ticks=f['ticks_12mhz']-CORRECTION,message_hex=f['message_hex'],emitted_rf_elapsed=at,rf_age_s=(hub.relay.anchor-f['ticks_12mhz'])/12000000))
 hub=SourceHub(enabled,clock=lambda:now[0],sink=sink,max_age=3);hub.begin_epoch(cases[0]['epoch']);hub.start();admit=Admission(hub,3);history=StockHistory();frozen_hist=StockHistory()
 for r in stock:frozen_hist.append(r)
 frozen=frozen_hist.snapshot();stream=Stream1090Method(stage/'stream1090');executor=concurrent.futures.ThreadPoolExecutor(max_workers=1);stream_jobs={};stream_rows={};stream_errors={};stream_at=0;pointer=0;submitted=0;max_pool_pending=0;full=[];audits=[]
 try:
  warm=Assembler(100).feed(-1,0,0,bytes([127,127])*TOTAL);i=0;ready=False
  while not ready:
   if time.monotonic()>deadline:raise RuntimeError('Warmup deadline')
   while i<len(warm) and len(pool.pending)<pool.max_pending_jobs:pool.submit(warm[i]);i+=1
   ready=pool.pop() is not None;pool.take_completed();await asyncio.sleep(.002)
  cpu_before=sum(pool.cpu_seconds.values());origin=time.monotonic();last_snapshot=-1.;last_progress=0.;frames=history.snapshot();closed_rf=(cases[-1]['first']-first_sample+TOTAL)/2400000
  while True:
   now[0]=(time.monotonic()-origin)/args.scale
   if time.monotonic()>deadline:raise RuntimeError('Replay deadline')
   while pointer<len(stock) and stock[pointer]['arrival']<=rf_wall+now[0]:
    r=stock[pointer];history.append(r);t=r['ticks']+CORRECTION;wire=beast(r['message_hex'],t);hub.stock(wire,dict(kind=51,ticks_12mhz=t,message_hex=r['message_hex']),hub.epoch,now=r['arrival']-rf_wall);pointer+=1
   if time.monotonic()-last_snapshot>=.1:
    frames=history.snapshot();last_snapshot=time.monotonic()
   watermark=hub.relay.anchor-CORRECTION if hub.relay.anchor is not None else None
   while submitted<len(todos) and todos[submitted][0]<=now[0] and len(pool.pending)<pool.max_pending_jobs:
    due,b=todos[submitted];b.queued=origin+due*args.scale;references=[dict(r,seconds=(r['ticks']-b.first*5)/12000000) for r in frames] if methods['sic'] else ();pool.submit(b,references);submitted+=1
   r=pool.pop()
   if r is not None:complete.append(r)
   for b,events,work in pool.take_completed():
    raw_parts[b.first].extend(events);admit.offer(b,events,now[0])
   while stream_at<len(cases):
    c=cases[stream_at];due=(c['first']-first_sample+TOTAL)/2400000
    if now[0]<due or watermark is None or watermark<(c['first']+HALO+CORE)*5:break
    if sum(not f.done() for f in stream_jobs.values())>=2:break
    stream_jobs[c['first']]=executor.submit(stream.decode,c['_raw'],c['first'],frames);stream_at+=1
   for first,f in list(stream_jobs.items()):
    if f.done() and first not in stream_rows:
     events,cpu=f.result();stream_rows[first]=events;stream_errors[first]=stream.last_error;admit.offer_stream1090(hub.epoch,first,events,now[0])
   admit.drain(frames,watermark,now[0]);max_pool_pending=max(max_pool_pending,len(pool.pending));await asyncio.sleep(.02)
   if time.monotonic()-last_progress>=5:
    out.with_suffix('.progress.json').write_text(json.dumps(dict(virtual_rf_elapsed=now[0],submitted=submitted,complete=len(complete),stream_complete=len(stream_rows),pending_jobs=len(pool.pending),pending_admission=len(admit.pending))));last_progress=time.monotonic()
   if len(complete)==len(cases) and len(stream_rows)==len(cases) and not pool.pending and not admit.pending and now[0]>=closed_rf+.1:break
  await hub.settle();worker_cpu=sum(pool.cpu_seconds.values())-cpu_before;wall=time.monotonic()-origin
  grouping=[];baseline_stream=Stream1090Method(stage/'stream1090');stream_raw_parity=[]
  for item,events,work in complete:
   epoch,first,rfwall,raw,queued=item;assert merge_events([raw_parts[first]])==events,'Tap changed original grouping';grouping.append(first)
   candidates=[dict(r,ticks=first*5+r['sample_4msps']*3) for r in events if HALO*5//3<=r['sample_4msps']<(HALO+CORE)*5//3 and r['source'] in SOURCES]
   external,cpu=baseline_stream.decode(raw,first,frozen);stream_raw_parity.append(dict(first=first,exact=external==stream_rows[first],live=len(stream_rows[first]),full=len(external)));candidates.extend(external)
   extra,audit,decisions=evaluate(frozen,candidates,(first+HALO)*5,(first+HALO+CORE)*5);full.extend(extra);audits.append(audit)
  _,missing=pair(full,emitted);_,additional=pair(emitted,full);actual=[r for b in data['base'] for r in b['extra']];_,actual_missing=pair(actual,emitted)
  # Duplicates within already-emitted extras, not payload-only repeats.
  duplicate_extras=0;seen=collections.defaultdict(list)
  for r in emitted:
   if any(abs(t-r['ticks'])<=1440 for t in seen[r['message_hex']]):duplicate_extras+=1
   seen[r['message_hex']].append(r['ticks'])
  stock_duplicates=sum(bool(pair([r],stock)[0]) for r in emitted)
  producer_set=[r for r in data['relay'] if any((c['first']+HALO)*5<=r['ticks']<(c['first']+HALO+CORE)*5 for c in cases)]
  actual_wire=[r for r in producer_set if not pair([r],stock)[0]];_,wire_missing=pair(actual_wire,emitted)
  assert all(valid_df17(r['message_hex']) and r['source'] in SOURCES and enabled.get(r['source']) for r in emitted)
  by={}
  for source in sorted(SOURCES):
   baseline=[r for r in full if r['source']==source];_,lost=pair(baseline,emitted);by[source]=dict(enabled=enabled.get(source,False),full_pipeline=len(baseline),emitted_attributed=sum(r['source']==source for r in emitted),lost_full_pipeline_any_source=len(lost))
  result=dict(label=args.label,platform=platform.platform(),rf_seconds=len(cases),rf_gaps=data.get('gaps',[]),clock_scale=args.scale,scope='Independent real algorithm futures and Stream1090 producer on fresh evaluation-only RF; clock scaled on quota-limited target, not a production real-time latency claim.',grouping_exact=len(grouping)==len(cases),stream_candidate_parity=stream_raw_parity,full_pipeline_extras=len(full),asynchronous_extras=len(emitted),lost_vs_full_pipeline=len(missing),additional_vs_full_pipeline=len(additional),actual_producer_extras=len(actual),lost_vs_actual_producer=len(actual_missing),actual_wire_extras=len(actual_wire),lost_vs_actual_wire=len(wire_missing),duplicate_extras=duplicate_extras,extras_matching_stock=stock_duplicates,hub=hub.report(),admission=dict(admit.count),methods=by,worker_cpu_s=worker_cpu,replay_wall_s=wall,max_pending_jobs=max_pool_pending,stream_report=stream.report(),stream_errors=stream_errors,alignment_verified_cases=sum(a['verified'] for a in audits),clock_mapping='Original final-chunk queued timestamp minus1.0005RF seconds, with measured realtime-minus-monotonic offset. USB/input buffering unmeasured. Stock arrival chronology retained.',fr24_attached=False,working_pipeline_changed=False)
  out.write_text(json.dumps(result,indent=2)+'\n');out.with_suffix('.private.json').write_text(json.dumps(dict(emitted=emitted,baseline=full,lost=missing,added=additional,actual_lost=actual_missing,wire_lost=wire_missing)));print(json.dumps({k:v for k,v in result.items() if k not in ['methods','stream_candidate_parity','stream_errors']}),flush=True)
 finally:
  await hub.close();executor.shutdown(wait=True);pool.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--scale',type=float,default=1);p.add_argument('--label',default='mac');p.add_argument('--timeout',type=float,default=360);p.add_argument('--job-runtime',type=Path);args=p.parse_args();asyncio.run(main(args))

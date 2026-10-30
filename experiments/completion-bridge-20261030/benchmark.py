"""Isolated contiguous real-time-paced RF replay; never opens receiver sockets."""
import collections,hashlib,json,sys,time
from pathlib import Path
import numpy as np
from bridge import Bridge,CompletionPool
from rescue.ring_transport import RingStreamingPool
from rescue.streaming import Assembler,HALO,CORE,TOTAL
from rescue.shadow import evaluate
from rescue.stock_history import StockHistory
from rescue.workers import merge_events
class Tapped(CompletionPool,RingStreamingPool):pass
def key(r):return r['message_hex'],r['ticks']
def match(r,rows):return any(p==r['message_hex'] and abs(t-r['ticks'])<=1440 for p,t in rows)
def describe(v):return dict(n=len(v),median=float(np.median(v)) if v else None,p95=float(np.percentile(v,95)) if v else None,p99=float(np.percentile(v,99)) if v else None,max=max(v) if v else None)
def main():
 stage=Path(sys.argv[1]);out=Path(sys.argv[2]);data=json.loads((stage/'capture/capture.private.json').read_text());assert not data['errors']
 cfg=json.loads((stage/'worker-config.json').read_text());methods=json.loads((stage/'method-config.json').read_text());enabled={**methods,'sequence':cfg['sequence_enabled'],'acquisition':cfg['acquisition_enabled']}
 selection=dict(workers=1,worker_cpus=[3],coherent_cpus=[3],config=cfg)
 pool=Tapped(stage/'models/tiny-fp32.onnx',methods,stage/'jobs-v3',selection,dispatch_ms=100,settle_s=.5)
 bridge=Bridge(enabled,max_age=3);stock=sorted(data['stock'],key=lambda r:r['arrival']);all_frames=StockHistory()
 for r in stock:all_frames.append(r)
 frozen=all_frames.snapshot();emitted=[];full=[];raw_candidates=[];cpu_bridge=0.;results=[];start=time.monotonic();deadline=start+180
 clock_offset=time.time()-time.monotonic();first=data['cases'][0];rf_wall=first['queued']+clock_offset-1.0005;first_sample=first['first'];pending_batches=[];raw_parts=collections.defaultdict(list);history=StockHistory();pointer=0
 for c in data['cases']:
  raw=(stage/'capture'/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256']
  batches=Assembler(100).feed(c['epoch'],c['first'],c['wall'],raw);assert len(batches)==10
  for b in batches:
   end=min(TOTAL,b.bounds[1]*120000+HALO);pending_batches.append(((b.first-first_sample+end)/2400000,b))
 try:
  warm=Assembler(100).feed(999,0,0,bytes([127,127])*TOTAL);todo=0;warmdone=False
  while not warmdone:
   if time.monotonic()>deadline:raise RuntimeError('Prewarm deadline')
   while todo<len(warm) and len(pool.pending)<pool.max_pending_jobs:pool.submit(warm[todo]);todo+=1
   warmdone=pool.pop() is not None;pool.take_completed();time.sleep(.002)
  cpu_before=sum(pool.cpu_seconds.values());origin=time.monotonic();submitted=0;lastdrain=0.;complete=[]
  while len(complete)<len(data['cases']) or pool.pending or bridge.pending:
   now=time.monotonic();elapsed=now-origin
   if now>deadline:raise RuntimeError('Benchmark deadline')
   while pointer<len(stock) and stock[pointer]['arrival']<=rf_wall+elapsed:history.append(stock[pointer]);pointer+=1
   frames=history.snapshot()
   while submitted<len(pending_batches) and len(pool.pending)<pool.max_pending_jobs and elapsed>=pending_batches[submitted][0]:
    due,b=pending_batches[submitted];b.queued=origin+due;pool.submit(b);submitted+=1
   result=pool.pop()
   if result is not None:complete.append(result)
   for b,rows,work in pool.take_completed():
    raw_parts[b.first].extend(rows);t=time.process_time();bridge.offer(b,rows,now);cpu_bridge+=time.process_time()-t
   if now-lastdrain>=.01:
    watermark=max((r['ticks'] for r in frames),default=None);t=time.process_time();emitted.extend(bridge.drain(frames,watermark,now,first_sample*5+elapsed*12000000));cpu_bridge+=time.process_time()-t;lastdrain=now
   time.sleep(.002)
  worker_cpu=sum(pool.cpu_seconds.values())-cpu_before;wall=time.monotonic()-origin
  for item,events,work in complete:
   epoch,first_sample_group,rfwall,raw,queued=item;assert merge_events([raw_parts[first_sample_group]])==events,'Grouping changed'
   candidates=[dict(r,ticks=first_sample_group*5+r['sample_4msps']*3) for r in events if HALO*5//3<=r['sample_4msps']<(HALO+CORE)*5//3 and r['source']!='broad_crc']
   extras,audit,decisions=evaluate(frozen,candidates,(first_sample_group+HALO)*5,(first_sample_group+HALO+CORE)*5)
   full.extend(extras);raw_candidates.extend(candidates);results.append(dict(first=first_sample_group,grouping_exact=True,alignment=audit,extras=len(extras),work=work))
 finally:pool.close()
 fullkeys=[key(r) for r in full];earlykeys=[key(r) for r in emitted];fast=[r for r in emitted if r['rf_age_s']<=.25];fastkeys=[key(r) for r in fast];actual=[key(r) for b in data['base'] for r in b['extra']];wire=[key(r) for r in data['relay']];by={}
 for source in ('energy','timing','soft','matched','coherent','neural'):
  base=[r for r in full if r['source']==source];own=[r for r in emitted if r['source']==source];quick=[r for r in fast if r['source']==source]
  by[source]=dict(full_replay=len(base),bridge_3s=len(own),under250ms=len(quick),baseline_retained_any_method=sum(match(r,earlykeys) for r in base),baseline_retained_under250_any_method=sum(match(r,fastkeys) for r in base),rf_age_s=describe([r['rf_age_s'] for r in own]),actual_producer_matches=sum(match(r,actual) for r in own),actual_relay_matches=sum(match(r,wire) for r in own))
 result=dict(scope='8 contiguous fresh RF seconds, real-time-paced isolated replay on core3 with35%one-core CPUQuota; restricted scheduling topology, not production latency.',rf_seconds=len(data['cases']),methods=by,total=dict(full_replay=len(full),bridge=len(emitted),under250ms=len(fast),baseline_missing=sum(not match(r,earlykeys) for r in full),early_not_in_full=sum(not match(r,fullkeys) for r in emitted),actual_producer=len(actual),actual_producer_retained=sum(match(dict(message_hex=p,ticks=t),earlykeys) for p,t in actual)),worker_cpu_s=worker_cpu,wall_s=wall,bridge_cpu_s=cpu_bridge,counters=dict(bridge.count),cases=results,stream1090='Independent producer, not a pool future; unchanged and excluded',clock_mapping='RF-time origin estimated from original final-chunk readiness minus1.0005s. USB buffering/earlier input latency unmeasured; under250ms is a replay estimate, not antenna-to-output proof.',tap_clock_offset_s=describe([c['wall']-(rf_wall+(c['first']-first_sample)/2400000) for c in data['cases']]))
 out.write_text(json.dumps(result,indent=2));out.with_suffix('.private.json').write_text(json.dumps(dict(emitted=emitted,full=full,raw=raw_candidates)));print(json.dumps({k:v for k,v in result.items() if k!='cases'}),flush=True)
if __name__=='__main__':main()

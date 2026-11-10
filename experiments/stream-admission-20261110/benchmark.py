"""Saved-RF, causal admission to an anonymous local sink. No production input/output."""
import argparse,collections,concurrent.futures as cf,hashlib,json,platform,resource,time
from pathlib import Path
import numpy as np
from bindings import Decoder
from bridge import Bridge
from final import Final
from rescue.fir_cached import FirBackend
from rescue.dsp import features,baseline,payloads,crc_batch,SAMPLES
from rescue.stock_history import StockHistory
from rescue.shadow import evaluate
from rescue.stream1090_shadow import compare
RATE=2400000

def stats(v):
 if not v:return {'n':0}
 v=sorted(v);q=lambda p:v[min(len(v)-1,int((len(v)-1)*p))]
 return dict(n=len(v),p50_ms=q(.5),p95_ms=q(.95),p99_ms=q(.99),max_ms=max(v),under250=sum(x<=250 for x in v),under250_with_50ms_clock_sensitivity=sum(x+50<=250 for x in v))
def match(r,rows):return any(r['message_hex']==s['message_hex'] and abs(r['ticks']-s['ticks'])<=1440 for s in rows)
class Energy:
 def __init__(self):self.backend=FirBackend()
 def block(self,path,index,first):
  t=time.thread_time();rows=[]
  for offset,core,iq in self.backend.iq_blocks(path,.05,(index,index+1)):
   starts,_=self.backend.candidate_scores(iq,core,.4)
   starts=starts[self.backend.header_ids(iq,starts)]
   for n in range(0,len(starts),512):
    pos=starts[n:n+512];pred=payloads(baseline(features(iq[pos[:,None]+np.arange(SAMPLES)[None,:]])));ok=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
    rows += [dict(source='energy',ticks=first*5+(offset+int(at))*3,message_hex=bytes(p).hex()) for at,p in zip(pos[ok],pred[ok])]
  return rows,time.thread_time()-t

def run(a,data,mode):
 cases=data['cases'];assert len(cases)==8 and len({c['epoch'] for c in cases})==1;origin_wall=cases[0]['wall'];first=cases[0]['first'];epoch=cases[0]['epoch'];raws=[]
 for c in cases:
  raw=(a.capture/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256'];raws.append(raw)
 decoder=Decoder(a.batch,a.incremental);energy=Energy();history=StockHistory();stock=sorted(data['stock'],key=lambda r:r['arrival']);cpu=collections.Counter();done=collections.Counter();queue=collections.Counter();native_rows=collections.defaultdict(list);energy_rows=collections.defaultdict(list)
 # Warm native table initialization off the evaluation RF and before timing.
 decoder.whole(bytes([127,127])*24000,0)
 final=Final(a.dedup,epoch);final.history=history;bridge=Bridge(epoch,final.extra,early=mode!='batch');pointer=0
 while pointer<len(stock) and stock[pointer]['arrival']<origin_wall:
  r=stock[pointer];history.append(r);final.stock(r,100+r['arrival']-origin_wall,False);pointer+=1
 jobs=[];contexts={}
 for i,c in enumerate(cases):
  bridge.begin(i,c);total=len(raws[i])//2;offset=c['wall']-origin_wall
  if mode=='batch':jobs.append((offset+total/RATE,'native',i,0,total,True))
  else:
   contexts[i]=decoder.begin(c['first'],total)
   for at in range(0,total,48000):
    stop=min(total,at+48000);jobs.append((offset+stop/RATE,'native',i,at,stop,stop==total))
  for index,at in enumerate(range(0,total,120000)):
   stop=min(total,at+120000);jobs.append((offset+min(total,stop+600)/RATE,'energy',i,index,stop,stop==total))
 jobs.sort(key=lambda x:x[0]);index=0;pending={'native':None,'energy':None};backlog={s:collections.deque() for s in pending};pools={s:cf.ThreadPoolExecutor(max_workers=1) for s in pending};started=time.monotonic();process=time.process_time();lastdrain=0;deadline=started+90
 def native_job(i,at,stop,last):
  t=time.thread_time();c=cases[i]
  if mode=='batch':rows=decoder.whole(raws[i],c['first'])
  else:
   rows=decoder.feed(contexts[i],raws[i][2*at:2*stop],c['first']+at)
   if last:rows+=decoder.finish(contexts[i])
  return rows,time.thread_time()-t
 try:
  while index<len(jobs) or any(pending.values()) or any(backlog.values()) or bridge.pending():
   now=time.monotonic();elapsed=now-started
   if now>deadline:raise TimeoutError('Owned replay deadline')
   while pointer<len(stock) and stock[pointer]['arrival']<=origin_wall+elapsed:
    r=stock[pointer];history.append(r);final.stock(r,100+elapsed,True);pointer+=1
   while index<len(jobs) and jobs[index][0]<=elapsed:
    job=jobs[index];backlog[job[1]].append(job);index+=1
   for source in pending:
    item=pending[source]
    if item is not None and item[0].done():
     f,j=item;rows,work=f.result();due,_,i,at,stop,last=j;cpu[source]+=work;done[source]+=1;c=cases[i]
     if source=='native':native_rows[i]+=rows;wm=c['first']*5+(stop//8208*8208)*5-6000
     else:energy_rows[i]+=rows;wm=c['first']*5+stop*5-6000
     if last:wm=(c['first']+600+RATE)*5+1440
     if source=='energy':
      lo=(c['first']+600)*5;rows=[r for r in rows if lo<=r['ticks']<lo+12000000]
     bridge.offer(i,source,epoch,rows,wm,last);pending[source]=None
    if pending[source] is None and backlog[source]:
     j=backlog[source].popleft();due,_,i,at,stop,last=j;queue[source]=max(queue[source],len(backlog[source])+1)
     f=pools[source].submit(native_job,i,at,stop,last) if source=='native' else pools[source].submit(energy.block,a.capture/cases[i]['file'],at,cases[i]['first']);pending[source]=(f,j)
   if now-lastdrain>=.005:
    t=time.thread_time();frames=history.snapshot();bridge.drain(frames,final.stock_watermark,elapsed);cpu['admission_main']+=time.thread_time()-t;lastdrain=now
   time.sleep(.001)
  measured_cpu=time.process_time()-process;wall=time.monotonic()-started
  # Tail is preserved for byte/late-stock checks, excluded from latency statistics.
  for r in stock[pointer:]:history.append(r);final.stock(r,100+max(wall,r['arrival']-origin_wall),False)
  cache=final.close()
 finally:
  for pool in pools.values():pool.shutdown(wait=True,cancel_futures=True)
  for ctx in contexts.values():decoder.close(ctx)
 full=history.snapshot();reference=[];raw_parity=True
 for i,c in enumerate(cases):
  expected=decoder.whole(raws[i],c['first']);raw_parity &= expected==native_rows[i]
  alignment,extras=compare(native_rows[i],[(r['ticks'],r['message_hex']) for r in full]);assert alignment['aligned']
  lo=(c['first']+600)*5;hi=lo+12000000
  out,audit,_=evaluate(full,[r for r in energy_rows[i] if lo<=r['ticks']<hi]+[dict(source='stream1090',ticks=t,message_hex=m) for t,m in extras if lo<=t<hi],lo,hi);assert audit['verified'];reference += [r for r in out if lo<=r['ticks']<hi]
 emitted=[r for r in final.records if r['source']!='stock'];recorded=[r for b in data['base'] for r in b['extra']];nonstream=[r for r in recorded if r['source']!='stream1090'];relay=data['relay'];metrics={}
 for source in ['energy','stream1090','all']:
  own=[r for r in emitted if source=='all' or r['source']==source];base=[r for r in reference if source=='all' or r['source']==source]
  lat=[1000*((r['received']-started)-((r['ticks']-first*5)/12000000+.000120)) for r in own]
  metrics[source]=dict(emitted=len(own),early=sum(r['lane']=='early' for r in own),fallback=sum(r['lane']=='final' for r in own),latency=stats(lat),deferred_reference=len(base),reference_retained_any_method=sum(match(r,emitted) for r in base),not_in_recorded_other_DSP=sum(not match(r,nonstream) for r in own),not_in_recorded_full_pipeline=sum(not match(r,recorded) for r in own),not_in_recorded_relay=sum(not match(r,relay) for r in own))
 stocklat=[1000*((r['received']-started)-(r['scheduled']-origin_wall)) for r in final.records if r['source']=='stock' and r['timed']]
 return dict(mode=mode,metrics=metrics,raw_batch_parity=raw_parity,worker_cpu_s=dict(cpu),total_process_cpu_s=measured_cpu,cpu_s_per_RF_s=measured_cpu/len(cases),wall_s=wall,stock_delivery_delay=stats(stocklat),stock_records=len(stock),stock_byte_sha256=final.actual_stock.hexdigest(),stock_bytes_preserved=True,bridge_counts=dict(bridge.count),relay_counts=dict(final.count),dedup=cache,maximum_backlog=dict(queue),events=emitted,energy_digest=hashlib.sha256(json.dumps(dict(energy_rows),sort_keys=True).encode()).hexdigest(),native_digest=hashlib.sha256(json.dumps(dict(native_rows),sort_keys=True).encode()).hexdigest())
def main():
 p=argparse.ArgumentParser();p.add_argument('--capture',type=Path,required=True);p.add_argument('--batch',type=Path,required=True);p.add_argument('--incremental',type=Path,required=True);p.add_argument('--dedup',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();data=json.loads((a.capture/'capture.private.json').read_text());assert not data['errors'];results=[run(a,data,m) for m in ['batch','20ms']];batch,inc=results
 retained=sum(match(r,inc['events']) for r in batch['events']);added=sum(not match(r,batch['events']) for r in inc['events']);assert batch['raw_batch_parity'] and inc['raw_batch_parity'];assert batch['native_digest']==inc['native_digest'];assert batch['energy_digest']==inc['energy_digest'];assert batch['stock_byte_sha256']==inc['stock_byte_sha256']
 private=a.output.with_suffix('.private.json');private.write_text(json.dumps(dict(results=results),indent=2)+'\n')
 for r in results:r.pop('events')
 summary=dict(platform=platform.platform(),rf_seconds=8,results=results,comparison=dict(batch_extras=batch['metrics']['all']['emitted'],retained=retained,lost=batch['metrics']['all']['emitted']-retained,incremental_not_in_batch=added),working_pipeline_changed=False,scope='Causal historical 8-second energy+Stream1090 replay to an anonymous RAM-only socket sink; other DSP represented only by recorded references. No live feeder or antenna latency claim.',clock_limit='Recorded case wall origin is estimated; original 20ms RF arrival times absent. +50ms sensitivity reported, not a guaranteed physical error bound.',peak_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024 if platform.system()=='Darwin' else 1),hashes={n:hashlib.sha256(getattr(a,n).read_bytes()).hexdigest() for n in ['batch','incremental','dedup']})
 a.output.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':main()

"""Two independent frontends/futures, one final Rust output stage, no feeder."""
import collections,concurrent.futures as cf,hashlib,json,multiprocessing as mp,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'completion-bridge-20261030'))
from admission import Admission
from rust_history import RustHistory
from rescue import workers
from rescue.streaming import Assembler,TOTAL,HALO,CORE
from rescue.stock_history import StockHistory
from rescue.shadow import evaluate
from rescue.feed import beast,CORRECTION,valid

def init(role,stage,q):
 stage=Path(stage);methods={k:False for k in ('energy','crc','timing','soft','matched','coherent','header','sic','neural','pulse')};methods.update(energy=True,coherent=False)
 cfg=json.loads((stage/'worker-config.json').read_text());tuning=dict(threshold=cfg['coherent_threshold'],budget=cfg['coherent_budget'],coherent_enabled=True,optimized_dsp=True,optimized_v3=True,optimized_extended=cfg['optimized_extended'],coherent_pair_retry=cfg['coherent_pair_retry'],share_frontend=False,sequence_model=str(stage/'models/pulse-sequence.json'),sequence_enabled=False,acquisition_enabled=False)
 workers.initialize(str(stage/'models/tiny-fp32.onnx'),methods,str(stage/'jobs'),q,None,'dsp' if role=='energy' else 'coherent',tuning)

def match(r,rows):return any(p==r['message_hex'] and abs(t-r['ticks'])<=1440 for p,t in rows)
def stats(v):
 if not v:return dict(n=0,median=None,p95=None,max=None)
 v=sorted(v);return dict(n=len(v),median=(v[len(v)//2]+v[(len(v)-1)//2])/2,p95=v[min(len(v)-1,int(len(v)*.95))],max=max(v))
class Final:
 def __init__(self,path):self.cache=RustHistory(path);self.wire=bytearray();self.stock_sha=hashlib.sha256();self.stock_expected=hashlib.sha256();self.extra=[];self.cpu=0.;self.stock_records=0
 def write(self,wire):
  if len(self.wire)+len(wire)>16*1024**2:raise RuntimeError('Final output RAM cap')
  self.wire.extend(wire)
 def stock(self,r,epoch,now):
  body=r['ticks_12mhz'].to_bytes(6,'big')+bytes([r['signal_byte']])+bytes.fromhex(r['message_hex']);wire=b'\x1a3'+body.replace(b'\x1a',b'\x1a\x1a')
  self.stock_expected.update(wire);t=time.process_time();assert self.cache.push('stock',epoch,r['ticks'],r['message_hex'],now,validated=True);self.cpu+=time.process_time()-t;self.stock_records+=1;self.stock_sha.update(wire);self.write(wire)
 def emit(self,r,now):
  a=r.get('alignment',{})
  if r.get('source') not in ('energy','coherent') or not valid(r.get('message_hex')) or a.get('verified') is not True or a.get('matches',0)<20 or a.get('median_abs_error_us',999)>2:raise ValueError('Unadmitted extra at final stage')
  t=time.process_time();accepted=self.cache.push(r['source'],r['epoch'],r['ticks'],r['message_hex'],now,validated=True);self.cpu+=time.process_time()-t
  if accepted:self.extra.append(dict(r));self.write(beast(r['message_hex'],r['ticks']+CORRECTION))

def main():
 stage=Path(sys.argv[1]);data=json.loads((stage/'capture/capture.private.json').read_text());assert not data['errors'];epoch=data['cases'][0]['epoch'];first=data['cases'][0]['first'];rfwall=data['cases'][0]['queued']+(time.time()-time.monotonic())-1.0005
 history=StockHistory();allhistory=StockHistory();stock=sorted(data['stock'],key=lambda r:r['arrival'])
 for r in stock:allhistory.append(r)
 frozen=allhistory.snapshot();ctx=mp.get_context('spawn');assignments={s:ctx.Queue(1) for s in ('energy','coherent')}
 for q in assignments.values():q.put(3)
 pools={s:cf.ProcessPoolExecutor(max_workers=1,mp_context=ctx,initializer=init,initargs=(s,str(stage),assignments[s])) for s in assignments};pending={s:[] for s in pools};cpu=collections.Counter();count=collections.Counter();completed=[];jobs=[];latencies=collections.defaultdict(list);queue_delay=collections.defaultdict(list);final=Final(stage/'build/dedup.so');admission=Admission(dict(energy=True,coherent=True),max_age=3);admission.begin_epoch(epoch);admission_cpu=0.;deadline=time.monotonic()+180
 for c in data['cases']:
  raw=(stage/'capture'/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256']
  for b in Assembler(50).feed(c['epoch'],c['first'],c['wall'],raw):
   p=stage/'jobs'/f'{b.first}-{b.bounds[0]}.uc8';p.parent.mkdir(exist_ok=True);p.write_bytes(b.raw);due=(b.first-first+min(TOTAL,b.bounds[1]*120000+HALO))/2400000;jobs.append((due,b,p))
 try:
  # Prime imports/native tables on non-evaluation zero-amplitude noise.
  w=stage/'warm.uc8';w.write_bytes(bytes([127,127])*TOTAL)
  warm=[p.submit(workers.decode_job,str(w),(0,1),(),0,TOTAL) for p in pools.values()]
  for f in warm:f.result(timeout=45)
  origin=time.monotonic();index=0;pointer=0;lastdrain=0.;missing=[]
  while index<len(jobs) or any(pending.values()) or admission.pending:
   now=time.monotonic();elapsed=now-origin
   if now>deadline:raise RuntimeError('Owned benchmark deadline')
   while pointer<len(stock) and stock[pointer]['arrival']<=rfwall+elapsed:
    r=stock[pointer];history.append(r);final.stock(r,epoch,now);pointer+=1
   while index<len(jobs) and jobs[index][0]<=elapsed:
    due,b,p=jobs[index]
    for source,pool in pools.items():
     if len(pending[source])>=4:count[source+'_queue_shed']+=1;missing.append((source,b,p));continue
     f=pool.submit(workers.decode_job,str(p),b.bounds,(),b.raw_start,TOTAL);pending[source].append((f,b,due,now))
    index+=1
   for source in pools:
    keep=[]
    for f,b,due,submitted in pending[source]:
     if not f.done():keep.append((f,b,due,submitted));continue
     rows,work=f.result();assert all(r['source']==source for r in rows),(source,set(r['source'] for r in rows));cpu[source]+=work['worker_cpu_s'];count[source+'_completed']+=1;completed.append((source,b,rows,work));latencies[source].append(now-origin-due);queue_delay[source].append(work['chunk_started_s']-submitted)
     t=time.process_time();admission.offer(b,rows,now);admission_cpu+=time.process_time()-t
    pending[source]=keep
   if now-lastdrain>=.01:
    frames=history.snapshot();watermark=max((r['ticks'] for r in frames),default=None);t=time.process_time();out=admission.drain(frames,watermark,now,first*5+elapsed*12e6);admission_cpu+=time.process_time()-t
    for r in out:final.emit(r,now)
    lastdrain=now
   time.sleep(.002)
  wall=time.monotonic()-origin;async_cpu=dict(cpu);final_count=dict(final.cache.count);final_entries=final.cache.size
  # Complete any queue-shed jobs only for baseline coverage, never emit them.
  for source,b,p in missing:
   rows,work=pools[source].submit(workers.decode_job,str(p),b.bounds,(),b.raw_start,TOTAL).result(timeout=30);completed.append((source,b,rows,work))
 finally:
  for p in pools.values():p.shutdown(wait=True,cancel_futures=True)
  for q in assignments.values():q.close();q.join_thread()
 baseline=[];raw_by_group=collections.defaultdict(list)
 for source,b,rows,work in sorted(completed,key=lambda v:(v[1].first,v[1].bounds[0],v[0])):raw_by_group[b.first].extend(rows)
 for c in data['cases']:
  rows=workers.merge_events([raw_by_group[c['first']]]);candidates=[dict(r,ticks=c['first']*5+r['sample_4msps']*3) for r in rows if HALO*5//3<=r['sample_4msps']<(HALO+CORE)*5//3];extras,audit,decisions=evaluate(frozen,candidates,(c['first']+HALO)*5,(c['first']+HALO+CORE)*5);assert audit['verified'];baseline.extend(extras)
 emitted=final.extra;keys=[(r['message_hex'],r['ticks']) for r in emitted];baselinekeys=[(r['message_hex'],r['ticks']) for r in baseline];actual=[(r['message_hex'],r['ticks']) for b in data['base'] for r in b['extra']];actualwire=[(r['message_hex'],r['ticks']) for r in data['relay']];result={}
 for source in pools:
  base=[r for r in baseline if r['source']==source];own=[r for r in emitted if r['source']==source];ages=[];fast=0
  for r in base:
   a=[e['rf_age_s'] for e in emitted if e['message_hex']==r['message_hex'] and abs(e['ticks']-r['ticks'])<=1440]
   if a:ages.append(min(a));fast+=min(a)<=.25
  result[source]=dict(grouped_baseline=len(base),retained_any_method=len(ages),under250_any_method=fast,emitted_attribution=len(own),retained_age_s=stats(ages),completion_after_input_ready_s=stats(latencies[source]),queue_wait_s=stats(queue_delay[source]),worker_cpu_s=async_cpu[source])
 assert final.stock_sha.digest()==final.stock_expected.digest();assert all(valid(r['message_hex']) for r in emitted)
 summary=dict(methods=result,rf_seconds=8,total=dict(baseline=len(baseline),emitted=len(emitted),retained_baseline=sum(match(r,keys) for r in baseline),under250=sum(r['rf_age_s']<=.25 for r in emitted),not_in_grouped_baseline=sum(not match(r,baselinekeys) for r in emitted),not_in_recorded_full_pipeline=sum(not match(r,actual) for r in emitted),not_in_actual_relay=sum(not match(r,actualwire) for r in emitted)),wall_s=wall,admission_cpu_s=admission_cpu,final_dedup_cpu_s=final.cpu,final_dedup=final_count,final_history_entries=final_entries,stock_records=final.stock_records,stock_byte_hash=final.stock_sha.hexdigest(),stock_preserved=True,counts=dict(count),admission_counts=dict(admission.count),complete_baseline_jobs=len(completed),complete_baseline_worker_cpu_s={s:sum(w['worker_cpu_s'] for name,b,rows,w in completed if name==s) for s in pools},scheduled_jobs_per_method=len(jobs),scope='Reserved engineering RF; fully independent energy/coherent frontends and futures; core3/35%one-core quota; original pipeline/FR24 untouched; estimated pre-feeder RF ages, not cloud latency.')
 (stage/'result.json').write_text(json.dumps(summary,indent=2));(stage/'result.private.json').write_text(json.dumps(dict(emitted=emitted,baseline=baseline,completions=[dict(source=s,first=b.first,bounds=b.bounds,work=w) for s,b,rows,w in completed])));(stage/'output.beast').write_bytes(final.wire);final.cache.close();print(json.dumps(summary),flush=True)
if __name__=='__main__':main()

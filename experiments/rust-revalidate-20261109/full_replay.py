"""Exact copied current ring workers, offline full-method reference, no live output."""
import json,time,argparse,hashlib,os
from pathlib import Path
from rescue.ring_transport import RingStreamingPool
from rescue.streaming import Assembler,HALO,CORE
from rescue.stock_history import StockHistory
from rescue.shadow import evaluate
from rescue.workers import merge_events
p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cycles',type=int,default=1);a=p.parse_args()
def run():
 assert not a.output.exists();d=json.loads((a.stage/'input/dataset.private.json').read_text());methods=json.loads((a.stage/'methods.json').read_text());cfg=json.loads((a.stage/'workers.json').read_text());assert methods['sic'] is False;selection=dict(workers=2,worker_cpus=[3,3],coherent_cpus=[3,3],config=cfg)
 pool=RingStreamingPool(a.stage/'models/tiny-fp32.onnx',methods,a.stage/'jobs',selection,dispatch_ms=100,settle_s=0);out=[];start=time.process_time();began=time.monotonic()
 try:
  for i,c in enumerate(d['rows']*a.cycles):
   raw=(a.stage/'input/rf'/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256'];batches=Assembler(100).feed(c['epoch'],c['first'],c['wall'],raw);assert len(batches)==10;at=0;deadline=time.monotonic()+120
   while True:
    if time.monotonic()>deadline:raise RuntimeError('Bounded baseline timeout')
    while at<len(batches) and len(pool.pending)<pool.max_pending_jobs:pool.submit(batches[at]);at+=1
    r=pool.pop()
    if r is not None:break
    time.sleep(.005)
   item,events,work=r;assert item[0]==c['epoch'] and item[1]==c['first'];candidates=[dict(e,ticks=c['first']*5+e['sample_4msps']*3) for e in events if e['source']!='broad_crc' and HALO*5//3<=e['sample_4msps']<(HALO+CORE)*5//3];history=StockHistory()
   for f in c['stock']:history.append(f)
   accepted,audit,decisions=evaluate(history.snapshot(),candidates,(c['first']+HALO)*5,(c['first']+HALO+CORE)*5)
   out.append(dict(file=c['file'],candidates=candidates,accepted=accepted,audit=audit,decisions=decisions,work=work));a.output.with_suffix('.progress.json').write_text(json.dumps(dict(completed_cases=len(out),total=len(d['rows']))));print(json.dumps(dict(case=i,raw=len(candidates),accepted=len(accepted),alignment=audit)),flush=True)
  a.output.write_text(json.dumps(dict(cycles=a.cycles,observed_wall_s=time.monotonic()-began,cases=out,worker_cpu_s=sum(pool.cpu_seconds.values()),coordinator_cpu_s=time.process_time()-start,selection=selection,scope='Same ring/native/Rust algorithms and four workers; isolated single-core35% quota alters scheduling only; offline output is quarantined.'))+'\n')
 finally:pool.close()
if __name__=='__main__':run()

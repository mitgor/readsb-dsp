"""Historical reserved RF replay: test callback/whole-second grouping, not fresh validation."""
import hashlib,json,os,sys,tempfile,time
from pathlib import Path
from prototype import BatchTap
from rescue.streaming import Assembler,StreamingPool,TOTAL,RATE
from rescue.pipeline import settings
from rescue.workers import merge_events
class Tapped(BatchTap,StreamingPool):pass
def run(kind,raw):
 batches=Assembler(100).feed(1,0,0,raw);assert len(batches)==10
 with tempfile.TemporaryDirectory(prefix='latency-pool-parity-') as d:
  pool=kind('unused',settings(),Path(d),dict(workers=2,worker_cpus=[]),settle_s=.5);submitted=0;early=[];first=None;whole=None;start=time.monotonic();deadline=start+120
  try:
   while whole is None and time.monotonic()<deadline:
    elapsed=time.monotonic()-start
    while submitted<len(batches) and len(pool.pending)<pool.max_pending_jobs and elapsed>=(submitted+1)*.1:
     batches[submitted].queued=start+(submitted+1)*.1
     pool.submit(batches[submitted]);submitted+=1
    whole=pool.pop()
    if isinstance(pool,Tapped):
     for batch,rows,work in pool.pop_batches():
      if first is None:first=time.monotonic()-start
      early.append(rows)
    time.sleep(.001)
   assert whole is not None
   events=whole[1];return dict(events=events,early=merge_events(early),first_early_s=first,whole_ready_s=time.monotonic()-start,worker_cpu_s=sum(pool.cpu_seconds.values()),early_batches=len(early))
  finally:pool.close()
def main():
 p=Path(sys.argv[1]);raw=p.read_bytes()[:TOTAL*2];assert len(raw)==TOTAL*2
 baseline=run(StreamingPool,raw);tap=run(Tapped,raw)
 assert baseline['events']==tap['events'],'Tap changed full-second output'
 # Cross-batch priorities can differ before the full group settles; report exact
 # equality rather than silently normalizing samples or discarding differences.
 result=dict(rf_sha256=hashlib.sha256(raw).hexdigest(),scope='One historical reserved RF second. File transport, energy/CRC/timing/soft/matched only. Not full live pipeline or fresh admission validation.',whole_second_exact_parity=True,baseline_events=len(baseline['events']),tapped_events=len(tap['events']),early_union_exact_parity=tap['early']==baseline['events'],early_union_events=len(tap['early']),early_batches=tap['early_batches'],first_early_batch_s=tap['first_early_s'],whole_ready_s=tap['whole_ready_s'],baseline_whole_ready_s=baseline['whole_ready_s'],baseline_worker_cpu_s=baseline['worker_cpu_s'],tap_worker_cpu_s=tap['worker_cpu_s'])
 Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()

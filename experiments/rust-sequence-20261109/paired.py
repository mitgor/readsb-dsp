"""Same persistent workers alternate only sequence batch ABI per complete RF second."""
from pathlib import Path
import argparse,json,time,hashlib,statistics
from rescue.ring_transport import RingStreamingPool
from rescue.streaming import Assembler,HALO,CORE
from rescue.stock_history import StockHistory
from rescue.shadow import evaluate
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();D=a.root

def main():
 data=json.loads((D/'input/dataset.private.json').read_text());reference={r['file']:r for r in json.loads((D/'full-c.private.json').read_text())['cases']};methods=json.loads((D/'methods.json').read_text());cfg=json.loads((D/'workers.json').read_text());selection=dict(workers=2,worker_cpus=[3,3],coherent_cpus=[3,3],config=cfg);pool=RingStreamingPool(D/'models/tiny-fp32.onnx',methods,D/'paired-jobs',selection,dispatch_ms=100,settle_s=0);rows=[]
 def run(case,mode):
  assert not pool.pending;pool.ring.sequence_mode.value=mode;raw=(D/'input/rf'/case['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==case['sha256'];batches=Assembler(100).feed(case['epoch'],case['first'],case['wall'],raw);at=0;before=sum(pool.cpu_seconds.values());deadline=time.monotonic()+120
  while True:
   assert time.monotonic()<deadline,'Bounded paired RF timeout'
   while at<len(batches) and len(pool.pending)<pool.max_pending_jobs:pool.submit(batches[at]);at+=1
   r=pool.pop()
   if r is not None:break
   time.sleep(.005)
  item,events,work=r;cpu=sum(pool.cpu_seconds.values())-before;candidates=[dict(e,ticks=case['first']*5+e['sample_4msps']*3) for e in events if e['source']!='broad_crc' and HALO*5//3<=e['sample_4msps']<(HALO+CORE)*5//3];h=StockHistory()
  for f in case['stock']:h.append(f)
  accepted,audit,decisions=evaluate(h.snapshot(),candidates,(case['first']+HALO)*5,(case['first']+HALO+CORE)*5);ref=reference[case['file']]
  for field,value in [('candidates',candidates),('accepted',accepted),('audit',audit),('decisions',decisions)]:
   # Frozen JSON witnesses encode tuple-valued repair metadata as lists.
   # Round-trip the fresh record through the identical output contract, preserving
   # values, multiplicity and order; no sorting or dropped fields.
   assert ref[field]==json.loads(json.dumps(value)),(mode,case['file'],field)
  return dict(cpu_s=cpu,sequence_attributed_cpu_s=work.get('cpu_method_sequence_s'),dsp_neural_cpu_s=work.get('cpu_method_neural_s'),extras=len(accepted))
 try:
  # Same shared four workers: warm both ABIs before timing, full output rechecked.
  run(data['rows'][0],0);run(data['rows'][0],1)
  for cycle in range(2):
   for i,c in enumerate(data['rows']):
    pair={}
    for mode in ([0,1] if (cycle+i)%2==0 else [1,0]):pair['rust' if mode else 'optimized_C']=run(c,mode)
    rows.append(dict(cycle=cycle,file=c['file'],modes=pair));print(cycle,i,pair,flush=True)
  totals={mode:sum(row['modes'][mode]['cpu_s'] for row in rows) for mode in ['optimized_C','rust']};out=dict(paired_RF_seconds_per_mode=len(rows),warmup_RF_seconds=2,all_raw_and_guarded_events_exact=True,pairs=rows,total_worker_CPU_s=totals,worker_CPU_per_RF_second={k:v/len(rows) for k,v in totals.items()},worker_CPU_reduction_percent=100*(1-totals['rust']/totals['optimized_C']),median_paired_reduction_percent=statistics.median(100*(1-r['modes']['rust']['cpu_s']/r['modes']['optimized_C']['cpu_s']) for r in rows),scope='Alternating sequence-only ABI switch on shared persistent workers. All other libraries and prepared templates fixed to rebuilt optimized-C baseline; historical RF, no live output.');(D/'paired.json').write_text(json.dumps(out,indent=2)+'\n')
 finally:pool.close()
if __name__=='__main__':main()

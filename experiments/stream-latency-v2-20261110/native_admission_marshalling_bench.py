"""Balanced isolated wrapper microbenchmark, not whole-pipeline CPU evidence."""
import argparse,ctypes as C,importlib.util,json,statistics,time
from pathlib import Path
from native_admission import NativeAdmission
from native_admission_tests import payload

def main():
 p=argparse.ArgumentParser();p.add_argument('--library',type=Path,required=True);p.add_argument('--baseline-python',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--iterations',type=int,default=1000);a=p.parse_args();assert not a.output.exists();spec=importlib.util.spec_from_file_location('uncached_native_admission',a.baseline_python);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);result=[]
 for count in [20,96,256]:
  anchors=[dict(source='energy',ticks=1_000_000_000+i*10000,message_hex=payload(i+1)) for i in range(count)];candidates=anchors+[dict(source='stream1090',ticks=anchors[-1]['ticks']+50000+i*2000,message_hex=payload(count+1+i)) for i in range(4)];cost={'old':[],'cached':[]};marshal={'old':[],'cached':[]}
  for repeat in range(4):
   engines={'old':old.NativeAdmission(a.library),'cached':NativeAdmission(a.library)}
   for e in engines.values():e.append_stocks(anchors)
   expected=engines['old'].evaluate(candidates,0,2**62);assert engines['cached'].evaluate(candidates,0,2**62)==expected
   for name in (['old','cached'] if repeat%2==0 else ['cached','old']):
    e=engines[name]
    for _ in range(20):e.evaluate(candidates,0,2**62)
    start=time.process_time()
    for _ in range(a.iterations):e.evaluate(candidates,0,2**62)
    cost[name].append(time.process_time()-start)
    start=time.process_time()
    if name=='cached':
     for _ in range(a.iterations):e._rows(candidates)
    else:
     for _ in range(a.iterations):(old.Row*len(candidates))(*(old.row(r) for r in candidates))
    marshal[name].append(time.process_time()-start)
   for e in engines.values():e.close()
  summary=dict(candidates=len(candidates),iterations=a.iterations,repeats=4,exact_output_parity=True,CPU_s=cost,marshalling_CPU_s=marshal,median_total_reduction_pct=100*(1-statistics.median(cost['cached'])/statistics.median(cost['old'])),median_marshalling_reduction_pct=100*(1-statistics.median(marshal['cached'])/statistics.median(marshal['old'])));result.append(summary)
 a.output.write_text(json.dumps(dict(scope='Synthetic repeated-anchor wrapper microbenchmark; unchanged Rust engine. Not RF throughput or end-to-end latency evidence.',rows=result),indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

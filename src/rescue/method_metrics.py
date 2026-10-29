"""CPU accounting for attributed recovery; never claim ablation/energy savings."""
import time
from collections import Counter
METHODS=('energy','timing','soft','matched','coherent','sequence','acquisition','pulse','header','sic','neural','crc')
class MethodMetrics:
 def __init__(self):self.started=time.monotonic();self.cpu=Counter();self.total_cpu=0.;self.windows=0
 def record(self,work):
  self.windows+=1;self.total_cpu+=sum(c.get('worker_cpu_s',0) for c in work.get('chunks',[]))
  for name in METHODS:self.cpu[name]+=max(0.,work.get('cpu_method_'+name+'_s',0.))
 def report(self,distance):
  duration=max(time.monotonic()-self.started,1.e-6);total=max(self.total_cpu,sum(self.cpu.values()));extras=sum(distance.get(k+'_extra',0) for k in METHODS if k!='crc');rows={}
  for k in METHODS:
   n=distance.get(k+'_extra',0) if k!='crc' else distance.get('crc_research_extra',0);cpu=self.cpu[k]
   rows[k]=dict(cpu_seconds=cpu,mean_core_percent=100*cpu/duration,cpu_share_percent=100*cpu/total if total else None,additional_packets=n,cpu_ms_per_additional=1000*cpu/n if n else None,relative_cpu_per_detection=(cpu/total)/(n/extras) if k!='crc' and total and n and extras else None)
  return dict(methods=rows,elapsed_wall_s=duration,processed_windows=self.windows,total_worker_cpu_seconds=total,shared_frontend_and_overhead_cpu_seconds=max(0.,total-sum(self.cpu.values())),attribution='Exclusive measured CPU; shared coherent carrier fits apportioned by candidate membership. Shared FIR/frontend and coordinator overhead are not assigned to methods. Relative cost = method CPU share / method attributed-extra share; lower is cheaper. This is not an ablation, wattage or causal marginal-recovery measurement. Broad CRC counts are research-only and not feeder-eligible.')

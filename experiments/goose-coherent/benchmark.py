"""Fresh-process CPU/RSS benchmark, output parity first, compiler time excluded."""
import argparse,hashlib,json,platform,statistics,struct,subprocess,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent

def compare(reference,other,n):
 x=reference.read_bytes();y=other.read_bytes();at=0;results={}
 for key,typ,count in [('logits','<f8',112*n),('confidence','<f8',112*n),('tracked','u1',n),('frequency','<f8',n),('inliers','<i4',n),('rows','u1',14*n),('flips','i1',2*n),('valid','u1',n)]:
  a=np.frombuffer(x,typ,count,at);b=np.frombuffer(y,typ,count,at);at+=np.dtype(typ).itemsize*count
  if key in ('logits','confidence','frequency'):
   assert np.allclose(a,b,rtol=1e-12,atol=1e-15,equal_nan=True),key
   results[key+'_max_abs']=float(np.nanmax(abs(a-b)))
   if key=='logits':assert np.array_equal(a>0,b>0),'hard bits differ'
  else:assert np.array_equal(a,b),key
  if key=='valid':results['noise_valid']=int(np.count_nonzero(b[-32:]));assert results['noise_valid']==0
 assert at==len(x)==len(y)
 results.update(packet_rows_flags_repairs_exact=True,hard_bits_exact=True)
 return results

def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=HERE/'.work');p.add_argument('--output',type=Path,required=True);p.add_argument('--trials',type=int,default=7);a=p.parse_args();w=a.work.resolve();n=struct.unpack('<Q',(w/'windows.bin').read_bytes()[:8])[0]
 if a.output.exists():raise ValueError('Choose fresh output')
 variants=['c','goose','c-sort'];raw=[];correctness={}
 def run(name,loops):
  out=w/(name+'.out');exe=w/(name+'-bench');r=json.loads(subprocess.check_output([str(exe),str(w/'windows.bin'),str(loops),str(out)],text=True));r.update(variant=name,peak_rss_mib=r['peak_rss_bytes']/1048576,cpu_us_per_window=1e6*r['cpu_seconds']/(n*loops));return r
 warm={name:run(name,1) for name in variants}
 for name in ['goose','c-sort']:correctness[name]=compare(w/'c.out',w/(name+'.out'),n)
 loops=max(1,min(10000,round(.5/max(warm['c']['cpu_seconds'],1e-5))))
 for trial in range(a.trials):
  order=variants[trial%3:]+variants[:trial%3]
  if trial%2:order=list(reversed(order))
  for name in order:
   r=run(name,loops);r.update(trial=trial);raw.append(r)
   compare(w/'c.out',w/(name+'.out'),n)
  print('trial',trial+1,'of',a.trials,flush=True)
 summary={}
 for name in variants:
  rows=[r for r in raw if r['variant']==name];values=[r['cpu_us_per_window'] for r in rows];rss=[r['peak_rss_bytes'] for r in rows]
  summary[name]=dict(median_cpu_us_per_window=statistics.median(values),min_cpu_us_per_window=min(values),max_cpu_us_per_window=max(values),median_peak_rss_bytes=statistics.median(rss),min_peak_rss_bytes=min(rss),max_peak_rss_bytes=max(rss),median_resident_after_work_bytes=1024*statistics.median(r['rss_after_work_kb'] for r in rows),median_vm_kb=statistics.median(r['vm_after_work_kb'] for r in rows),binary_bytes=(w/(name+'-bench')).stat().st_size,valid=rows[0]['valid'],tracked=rows[0]['tracked'])
 for name in ['goose','c-sort']:summary[name]['cpu_change_percent_vs_c']=100*(summary[name]['median_cpu_us_per_window']/summary['c']['median_cpu_us_per_window']-1)
 result=dict(hardware=platform.platform(),compiler=subprocess.check_output(['cc','--version'],text=True).splitlines()[0],flags=['-O3','-std=c11','-ffp-contract=off'],trials=a.trials,loops=loops,windows=n,fixture_sha256=hashlib.sha256((w/'windows.bin').read_bytes()).hexdigest(),correctness=correctness,summary=summary,samples=raw,live_changes=False,policy='Identical preallocated harness and input; 2 warmups/process; initialization/IO excluded from timed CPU. RSS is whole executable: Linux exec-local /proc/self/status VmHWM (not inherited getrusage ru_maxrss), macOS getrusage; current resident memory also sampled. VM reservations separate. C-sort is a hybrid attribution control, not a deployment or pure-C memory comparison.')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

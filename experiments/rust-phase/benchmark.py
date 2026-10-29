"""Matched full-EM C/Rust timing and complete output parity; no live input."""
import argparse,hashlib,json,platform,shutil,statistics,struct,subprocess
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=HERE/'.work');p.add_argument('--output',type=Path,required=True);a=p.parse_args();w=a.work.resolve();assert not a.output.exists();n=struct.unpack('<Q',(w/'windows.bin').read_bytes()[:8])[0]
def compare():
 x=(w/'c.out').read_bytes();y=(w/'rust.out').read_bytes();at=0;result={}
 for name,typ,count in [('logits','f8',112*n),('confidence','f8',112*n),('rows','u1',14*n),('flips','i1',2*n),('valid','u1',n),('frequency','f8',n)]:
  one=np.frombuffer(x,typ,count,at);two=np.frombuffer(y,typ,count,at);at+=np.dtype(typ).itemsize*count
  if typ=='f8':assert np.allclose(one,two,rtol=1e-12,atol=1e-12,equal_nan=True),name;result[name+'_max_abs']=float(np.nanmax(abs(one-two)))
  else:assert np.array_equal(one,two),name
  if name=='logits':assert np.array_equal(one>0,two>0)
  if name=='valid':assert not two[-32:].any()
 assert at==len(x)==len(y);result.update(exact_all_arrays=x==y,packets_repairs_hard_bits_exact=True,noise_valid=0);return result
out={'platform':platform.platform(),'windows':n,'trials':9,'fixture_sha256':hashlib.sha256((w/'windows.bin').read_bytes()).hexdigest(),'iterations':{},'build':json.loads((w/'build.json').read_text()),'scope':'Full bounded EM method=0, iterations 1/2/4; identical precomputed seeds/initial decisions, same libm semantics, no live input or deployment.'}
for iterations in [1,2,4]:
 def run(name,loops):
  r=json.loads(subprocess.check_output([str(w/(name+'-bench')),str(w/'windows.bin'),str(loops),str(iterations),str(w/(name+'.out'))],text=True));r['cpu_us_per_window']=1e6*r['cpu_seconds']/(loops*n);return r
 warm=run('c',1);run('rust',1);parity=compare();loops=max(1,round(.3/warm['cpu_seconds']));samples={'c':[],'rust':[]}
 for trial in range(9):
  for name in (['c','rust'] if trial%2==0 else ['rust','c']):samples[name].append(run(name,loops));compare()
 summary={name:{'cpu_us_per_window':statistics.median(s['cpu_us_per_window'] for s in rows),'min_cpu_us':min(s['cpu_us_per_window'] for s in rows),'max_cpu_us':max(s['cpu_us_per_window'] for s in rows),'resident_bytes':statistics.median(s['resident_bytes'] for s in rows),'peak_rss_bytes':statistics.median(s['peak_rss_bytes'] for s in rows),'virtual_bytes':statistics.median(s['virtual_bytes'] for s in rows),'valid_window_outputs':rows[0]['valid']} for name,rows in samples.items()}
 out['iterations'][str(iterations)]={'parity':parity,'summary':summary,'loops':loops,'samples':samples,'cpu_saving_percent':100*(1-summary['rust']['cpu_us_per_window']/summary['c']['cpu_us_per_window'])};print('iterations',iterations,'saving',out['iterations'][str(iterations)]['cpu_saving_percent'],flush=True)
 # Test output beyond batch boundary by repeating one window as a separate call
 # is unnecessary: this kernel is independent per window and all arrays compared.
out['size_audit']={}
for name in ['c','rust']:
 original=w/(name+'-bench');copy=w/(name+'-stripped');shutil.copy2(original,copy);subprocess.run(['strip','-S',str(copy)],check=True);out['size_audit'][name]={'raw_bytes':original.stat().st_size,'debug_stripped_bytes':copy.stat().st_size,'sha256':hashlib.sha256(original.read_bytes()).hexdigest()}
a.output.write_text(json.dumps(out,indent=2)+'\n')

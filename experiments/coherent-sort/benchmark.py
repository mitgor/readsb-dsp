"""Compare C typed sort with libc, and gate deployment against installed kernels."""
import argparse,ctypes as C,hashlib,json,platform,statistics,struct,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=HERE/'.work');p.add_argument('--output',type=Path,required=True);p.add_argument('--live-root',type=Path);a=p.parse_args();w=a.work.resolve();w.mkdir(parents=True,exist_ok=True)
if a.output.exists():raise ValueError('Fresh output required')
f=w/'windows.bin';n=struct.unpack('<Q',f.read_bytes()[:8])[0];out={'windows':n,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'platform':platform.platform(),'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],'trials':7,'results':{},'installed_parity':{}}
flags=['-O3','-std=c11','-ffp-contract=off']+(['-D_DARWIN_C_SOURCE'] if platform.system()=='Darwin' else [])
out['flags']=flags;driver=ROOT/'experiments/goose-coherent/driver.c';source=ROOT/'src/rescue/coherent_kernel.c';iq=np.frombuffer(f.read_bytes(),dtype='<f4',offset=8).copy();starts=np.arange(n,dtype=np.int64)*480

def live_outputs(path):
 lib=C.CDLL(str(path));assert lib.rescue_coherent_init()==0
 fn=lib.rescue_coherent;fn.argtypes=[C.c_void_p,C.c_int64,C.c_void_p,C.c_int64]+[C.c_void_p]*8;fn.restype=C.c_int
 arrays=[np.zeros(n*112,np.float64),np.zeros(n*112,np.float64),np.zeros(n,np.uint8),np.zeros(n,np.float64),np.zeros(n,np.int32),np.zeros(n*14,np.uint8),np.zeros(n*2,np.int8),np.zeros(n,np.uint8)]
 assert fn(iq.ctypes.data,480*n,starts.ctypes.data,n,*[x.ctypes.data for x in arrays])==0
 assert not arrays[-1][-32:].any()
 return b''.join(x.tobytes() for x in arrays)

for mode,macros in [('base',[]),('pair',['-DRESCUE_COARSE_PAIR'])]:
 for name,extra in [('reference',['-DRESCUE_REFERENCE_SORT']),('typed',[])]:
  exe=w/(mode+'-'+name)
  subprocess.run(['cc',*flags,*macros,*extra,str(driver),str(source),'-lm','-lpthread','-o',str(exe)],check=True)
  subprocess.run(['cc',*flags,*macros,*extra,'-fPIC','-shared',str(source),'-lm','-lpthread','-o',str(exe)+'.so'],check=True)
 def run(name,loops):
  return json.loads(subprocess.check_output([str(w/(mode+'-'+name)),str(f),str(loops),str(w/(mode+'-'+name+'.out'))],text=True))
 warm=run('reference',1);run('typed',1);loops=max(1,round(.4/warm['cpu_seconds']))
 reference=(w/(mode+'-reference.out')).read_bytes();assert reference==(w/(mode+'-typed.out')).read_bytes()
 if a.live_root:
  installed=a.live_root/'src/rescue'/('_coherent.so' if mode=='base' else '_coherent_pair.so')
  assert live_outputs(installed)==reference,mode+' differs from installed baseline'
  out['installed_parity'][mode]={'exact_all_arrays':True,'sha256':hashlib.sha256(installed.read_bytes()).hexdigest()}
 rows={name:[] for name in ['reference','typed']}
 for trial in range(7):
  for name in (['reference','typed'] if trial%2==0 else ['typed','reference']):
   sample=run(name,loops);rows[name].append(sample);assert reference==(w/(mode+'-'+name+'.out')).read_bytes()
 result={name:{'cpu_us_per_window':statistics.median(s['cpu_seconds']*1e6/(loops*n) for s in samples),'resident_bytes':1024*statistics.median(s['rss_after_work_kb'] for s in samples),'samples':samples} for name,samples in rows.items()}
 result.update(saving_percent=100*(1-result['typed']['cpu_us_per_window']/result['reference']['cpu_us_per_window']),exact_output_parity=True,valid=warm['valid'],tracked=warm['tracked'],loops=loops)
 out['results'][mode]=result;print(mode,result['saving_percent'],'percent saving; exact output parity',flush=True)
subprocess.run(['cc','-O1','-g','-fsanitize=address,undefined','-I'+str(ROOT/'src/rescue'),str(HERE/'check_sort.c'),'-lm','-o',str(w/'check-sort-sanitize')],check=True)
out['sort_checks']=subprocess.check_output([str(w/'check-sort-sanitize')],text=True).strip()
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')

"""All-buffer sequence parity, controls and alternating CPU/RSS; never live I/O."""
from pathlib import Path
import argparse,ctypes as C,json,hashlib,time,statistics,platform,resource
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--trials',type=int,default=9);p.add_argument('--loops',type=int,default=3);a=p.parse_args();D=a.root;f=np.load(D/'input/windows.npz');iq=f['iq'];seeds=f['seeds'];h=f['h'];n=len(iq);libs={};pointer=lambda x:x.ctypes.data_as(C.c_void_p)
for name in ['c','rust',*(['actual'] if (D/'build/actual.so').exists() else [])]:
 l=C.CDLL(str(D/'build'/(name+'.so')));l.rescue_coherent_init.restype=C.c_int;assert l.rescue_coherent_init()==0;l.rescue_sequence_prepare.argtypes=[C.c_void_p]*4;l.rescue_sequence_prepare.restype=C.c_int;l.rescue_sequence_batch.argtypes=[C.c_void_p,C.c_int64,C.c_void_p,C.c_int64,*([C.c_void_p]*8)];l.rescue_sequence_batch.restype=C.c_int;libs[name]=l

def prepare(lib,h):
 hr=np.ascontiguousarray(h.real);hi=np.ascontiguousarray(h.imag);t=np.full((114,4,2,4,2),9.,np.float64);pre=np.full((24,2),9.,np.float64);rc=lib.rescue_sequence_prepare(*map(pointer,[hr,hi,t,pre]));return rc,t,pre

def execute(lib,x,seeds,templates,pre,count=None,starts=None):
 x=np.ascontiguousarray(x,np.complex64);seeds=np.ascontiguousarray(seeds,np.float64);count=len(x) if count is None else count;starts=np.arange(len(x),dtype=np.int64)*496+8 if starts is None else starts;l=np.full((len(x),112),88.,np.float64);c=l.copy();row=np.full((len(x),14),99,np.uint8);flips=np.full((len(x),2),99,np.int8);valid=np.full(len(x),99,np.uint8)
 rc=lib.rescue_sequence_batch(pointer(x),x.size,pointer(starts),count,*map(pointer,[seeds,templates,pre,l,c,row,flips,valid]));return rc,l,c,row,flips,valid

def exact(a,b,label):
 assert a[0]==b[0],(label,'return')
 for i,(x,y) in enumerate(zip(a[1:],b[1:])):
  if x.tobytes()!=y.tobytes():
   diff=np.abs(x.astype(float)-y.astype(float));raise AssertionError((label,i,int(np.count_nonzero(x!=y)),float(np.nanmax(diff))))

rc,templates,pre=prepare(libs['c'],h);assert rc==0;rng=np.random.default_rng(20261109);prep=0
for model in [h,np.zeros(9,complex),np.ones(9,complex),*list(rng.normal(0,.2,(32,9))+1j*rng.normal(0,.1,(32,9)))]:
 ref=prepare(libs['c'],model)
 for name,lib in libs.items():exact(ref,prepare(lib,model),('prepare',name))
 prep+=1
outputs={name:execute(lib,iq,seeds,templates,pre) for name,lib in libs.items()}
for name,output in outputs.items():exact(outputs['c'],output,('recorded',name))
controls={}
for label,x,sd,t in [('noise',(rng.normal(0,.01,(64,496))+1j*rng.normal(0,.01,(64,496))).astype(np.complex64),np.full(64,np.nan),templates),('zero',np.zeros((8,496),np.complex64),np.full(8,np.nan),templates),('frequency',iq[:128],np.linspace(-200000,200000,min(128,n)),templates),('generic',iq[:128],seeds[:128],templates.copy())]:
 if label=='generic':t[55,1,1,2,0]+=.001
 ref=execute(libs['c'],x,sd,t,pre)
 for name,lib in libs.items():exact(ref,execute(lib,x,sd,t,pre),(label,name))
 controls[label]=dict(windows=len(x),valid=int(ref[-1].sum()))
assert controls['noise']['valid']==0 and controls['zero']['valid']==0
# ABI bound/early-return behavior and untouched outputs.
for count,starts in [(-1,None),(4097,None),(1,np.array([7],np.int64)),(1,np.array([9],np.int64)),(0,None)]:
 x=iq[:1];sd=seeds[:1];ref=execute(libs['c'],x,sd,templates,pre,count,starts)
 for name,lib in libs.items():exact(ref,execute(lib,x,sd,templates,pre,count,starts),('bounds',count,str(starts),name))
# Fractional RF timing and complex phase/amplitude perturbations, never labels.
x=iq[:128].copy();x=(x*(np.exp(1j*np.linspace(-np.pi,np.pi,len(x)))[:,None])*.37).astype(np.complex64);x=(.75*x+.25*np.roll(x,1,axis=1)).astype(np.complex64);sd=np.full(len(x),np.nan);ref=execute(libs['c'],x,sd,templates,pre)
for name,lib in libs.items():exact(ref,execute(lib,x,sd,templates,pre),('RF_augmentation',name))
for _ in range(2):
 for lib in libs.values():execute(lib,iq,seeds,templates,pre)
trials=[];names=list(libs)
for trial in range(a.trials):
 times={};order=names[trial%len(names):]+names[:trial%len(names)]
 for name in order:
  start=time.process_time()
  for loop in range(a.loops):out=execute(libs[name],iq,seeds,templates,pre)
  times[name]=(time.process_time()-start)/a.loops;exact(outputs['c'],out,('timed',name))
 row=dict(trial=trial,cpu_s=times,saving_percent=100*(1-times['rust']/times['c']));trials.append(row);print(row,flush=True)
result=dict(platform=platform.platform(),windows=n,prepare_models=prep,all_arrays_bit_exact=True,valid_window_outputs=int(outputs['c'][-1].sum()),repaired_window_outputs=int(np.sum((outputs['c'][-2][:,0]>=0)&(outputs['c'][-1]>0))),controls=controls,augmented_windows=len(x),trials=trials,median_cpu_s={name:statistics.median(row['cpu_s'][name] for row in trials) for name in names},median_saving_percent=statistics.median(row['saving_percent'] for row in trials),fixture_sha256=hashlib.sha256((D/'input/windows.npz').read_bytes()).hexdigest(),libraries={name:hashlib.sha256((D/'build'/(name+'.so')).read_bytes()).hexdigest() for name in names},peak_python_process_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,production_changed=False,scope='Same optimized-v3 repeated-template sequence algorithm, generic-template fallback and CRC guards. Window outputs are not incremental full-pipeline transmissions. Includes identical Python allocation/FFI overhead; no live changes.')
(D/'benchmark.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['trials']},indent=2),flush=True)

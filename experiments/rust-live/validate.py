"""Gate both release libraries against the actually installed C libraries."""
import argparse,ctypes as C,hashlib,json,os,platform,statistics,struct,subprocess,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'experiments/goose-coherent'))
from benchmark import compare as strict_compare
def compare(reference,other,n):
 if platform.system()!='Darwin':return strict_compare(reference,other,n)
 # Apple complex codegen differs at roundoff level. Keep decisions exact;
 # use a 1e-12 absolute diagnostic tolerance, far below repair thresholds.
 one=reference.read_bytes();two=other.read_bytes();at=0;report={}
 for key,typ,count in [('logits','<f8',112*n),('confidence','<f8',112*n),('tracked','u1',n),('frequency','<f8',n),('inliers','<i4',n),('rows','u1',14*n),('flips','i1',2*n),('valid','u1',n)]:
  x=np.frombuffer(one,typ,count,at);y=np.frombuffer(two,typ,count,at);at+=np.dtype(typ).itemsize*count
  if typ=='<f8':assert np.allclose(x,y,rtol=1e-12,atol=1e-12,equal_nan=True),key;report[key+'_max_abs']=float(np.nanmax(abs(x-y)))
  else:assert np.array_equal(x,y),key
  if key=='logits':assert np.array_equal(x>0,y>0)
  if key=='valid':report['noise_valid']=int(np.count_nonzero(y[-32:]));assert report['noise_valid']==0
 assert at==len(one)==len(two)
 report.update(packet_rows_flags_repairs_exact=True,hard_bits_exact=True,mac_absolute_float_tolerance=1e-12)
 return report

p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--reference-root',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();w=a.work.resolve();n=struct.unpack('<Q',(w/'windows.bin').read_bytes()[:8])[0];assert not a.output.exists()
flags=['-O3','-std=c11','-ffp-contract=off']+(['-D_DARWIN_C_SOURCE'] if platform.system()=='Darwin' else [])
result={'windows':n,'fixture_sha256':hashlib.sha256((w/'windows.bin').read_bytes()).hexdigest(),'platform':platform.platform(),'branches':{},'controls':{},'trials':7}

def lib(path):
 l=C.CDLL(str(path));assert l.rescue_coherent_init()==0
 l.rescue_coherent.argtypes=[C.c_void_p,C.c_int64,C.c_void_p,C.c_int64]+[C.c_void_p]*8;l.rescue_coherent.restype=C.c_int
 l.rescue_coherent_peaks.argtypes=[C.c_void_p,C.c_int64,C.c_int64,C.c_int64,C.c_double,C.c_void_p];l.rescue_coherent_peaks.restype=C.c_int64
 return l

def outputs(l,iq):
 n=len(iq)//480;starts=np.arange(n,dtype=np.int64)*480
 arrays=[np.zeros(n*112,np.float64),np.zeros(n*112,np.float64),np.zeros(n,np.uint8),np.zeros(n,np.float64),np.zeros(n,np.int32),np.zeros(n*14,np.uint8),np.zeros(n*2,np.int8),np.zeros(n,np.uint8)]
 assert l.rescue_coherent(iq.ctypes.data,len(iq),starts.ctypes.data,n,*[x.ctypes.data for x in arrays])==0
 return b''.join(x.tobytes() for x in arrays)

for mode,name in [('base','_coherent.so'),('pair','_coherent_pair.so')]:
 old=a.reference_root.resolve()/'src/rescue'/name;new=a.candidate.resolve()/name;ref=lib(old);candidate=lib(new);candidate.rescue_coherent_backend.restype=C.c_char_p;marker=candidate.rescue_coherent_backend().decode();assert marker.startswith('rust-1.99.1/std-sort/')
 for label,path in [('reference',old),('rust',new)]:
  exe=w/(mode+'-'+label);subprocess.run(['cc',*flags,str(ROOT/'experiments/rust-live/abi_driver.c'),'-lm','-lpthread','-ldl','-o',str(exe)],check=True)
 def run(label,loops):return json.loads(subprocess.check_output([str(w/(mode+'-'+label)),str(w/'windows.bin'),str(loops),str(w/(mode+'-'+label+'.out'))],text=True,env={**os.environ,'COHERENT_LIBRARY':str(old if label=='reference' else new)}))
 warm=run('reference',1);run('rust',1);parity=compare(w/(mode+'-reference.out'),w/(mode+'-rust.out'),n)
 exact=(w/(mode+'-reference.out')).read_bytes()==(w/(mode+'-rust.out')).read_bytes()
 loops=max(1,round(.3/warm['cpu_seconds']));rows={'reference':[],'rust':[]}
 for trial in range(7):
  for label in (['reference','rust'] if trial%2==0 else ['rust','reference']):
   rows[label].append(run(label,loops));compare(w/(mode+'-reference.out'),w/(mode+'-'+label+'.out'),n)
 times={k:statistics.median(x['cpu_seconds']*1e6/(loops*n) for x in v) for k,v in rows.items()}
 result['branches'][mode]={'reference_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(new.read_bytes()).hexdigest(),'marker':marker,'parity':parity,'exact_all_arrays':exact,'cpu_us_per_window':times,'cpu_saving_percent':100*(1-times['rust']/times['reference']),'samples':rows,'valid':warm['valid'],'tracked':warm['tracked']}
 # Augment saved development RF only. Never treat these predictions as labels.
 seed=np.random.default_rng(20261029);original=np.frombuffer((w/'windows.bin').read_bytes(),'<c8',offset=8).copy();pool=original[:480*512].reshape(-1,480);stress=0
 for index in range(16):
  x=pool.copy();phase=seed.uniform(-np.pi,np.pi,(len(x),1));amp=10**seed.uniform(-2,1,(len(x),1));x=(x*np.exp(1j*phase)*amp).astype(np.complex64).reshape(-1)
  before=x.copy();(w/'stress-reference.out').write_bytes(outputs(ref,x));(w/'stress-rust.out').write_bytes(outputs(candidate,x))
  # Last 32 augmented RF windows are not noise controls; parse without that rule.
  at=0
  for dtype,count,key in [('f8',112*len(pool),'logits'),('f8',112*len(pool),'confidence'),('u1',len(pool),'tracked'),('f8',len(pool),'frequency'),('i4',len(pool),'inliers'),('u1',14*len(pool),'rows'),('i1',2*len(pool),'flips'),('u1',len(pool),'valid')]:
   left=np.frombuffer((w/'stress-reference.out').read_bytes(),dtype,count,at);right=np.frombuffer((w/'stress-rust.out').read_bytes(),dtype,count,at);at+=np.dtype(dtype).itemsize*count
   if dtype=='f8':assert np.allclose(left,right,rtol=1e-12,atol=1e-12,equal_nan=True),(mode,index,key)
   else:assert np.array_equal(left,right),(mode,index,key)
   if key=='logits':assert np.array_equal(left>0,right>0)
  assert np.array_equal(x,before);stress+=len(pool)
 peaks=0
 for test in range(500):
  score=np.round(seed.uniform(0,1,int(seed.integers(3,1200))),1).astype(np.float64);nr=len(score);one=np.empty(nr,np.int64);two=np.empty_like(one);core=int(seed.integers(0,nr+1));total=nr+480
  p1=ref.rescue_coherent_peaks(score.ctypes.data,nr,core,total,.35,one.ctypes.data);p2=candidate.rescue_coherent_peaks(score.ctypes.data,nr,core,total,.35,two.ctypes.data);assert p1==p2 and np.array_equal(one[:p1],two[:p2]);peaks+=1
 # ABI early-return guards use nulls safely, before accessing input/output.
 for size,expected in [(-1,-1),(4097,-1),(0,0)]:assert candidate.rescue_coherent(None,0,None,size,*([None]*8))==expected
 result['controls'][mode]={'augmented_windows':stress,'peak_selector_cases':peaks,'input_immutable':True,'invalid_count_and_empty_checks':True}
 print(mode,result['branches'][mode]['cpu_saving_percent'],'percent saving; parity passed',flush=True)
result['candidate_build']=json.loads((a.candidate/'build.json').read_text());a.output.write_text(json.dumps(result,indent=2)+'\n')

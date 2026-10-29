"""Offline release ABI/wrapper parity. No RF access or forwarding."""
import ctypes as C,hashlib,json,struct,sys,time
from pathlib import Path
import numpy as np
root=Path(sys.argv[1]).resolve(); out=Path(sys.argv[2]);sys.path.insert(0,str(root/'src'))
from rescue import research_science as s,coherent_extended_opt as a
assert a.backend_status()=='rust';assert s.backend_status()=={'em':'rust','sequence':'c','em_sequence':'c'}
b=(root/'windows.bin').read_bytes();n=struct.unpack('<Q',b[:8])[0];at=8
arrays=[]
for count,dtype in [(n*992,'f4'),(n,'f8'),(n*112,'f8'),(n*112,'f8')]:
 v=np.frombuffer(b,dtype,count,at).copy();at+=v.nbytes;arrays.append(v)
iq,seed,il,ic=arrays;h=np.array([1.,0,0,0,0,0,0,0,0]);hi=np.zeros(9);results={}
for iterations in [1,2,4]:
 outputs=[];timings={}
 for name,lib in [('c',s.library()),('rust',s.em_library())]:
  l=np.empty((n,112));c=np.empty_like(l);rows=np.empty((n,14),np.uint8);fl=np.empty((n,2),np.int8);valid=np.empty(n,np.uint8);freq=np.empty(n)
  t=time.process_time()
  for _ in range(3):assert lib.rescue_science(iq,n,seed,il,ic,h,hi,0,iterations,l,c,rows,fl,valid,freq)==0
  timings[name]=(time.process_time()-t)/3
  outputs.append([x.tobytes() for x in [l,c,rows,fl,valid,freq]])
 assert outputs[0]==outputs[1];assert not valid[-32:].any();results[str(iterations)]={'exact_all_arrays':True,'windows':n,'noise_valid':0,'cpu_seconds_per_batch':timings}
# Test actual wrappers, including retained C-only methods.
z=iq.reshape(n,496,2);z=(z[:,:,0]+1j*z[:,:,1]).astype(np.complex64)[:16]
rust=s.decode(z,h,iterations=2);saved=s.em_library;s.em_library=s.library
reference=s.decode(z,h,iterations=2);s.em_library=saved
assert rust[0]==reference[0]
for key in rust[1]:assert rust[1][key].tobytes()==reference[1][key].tobytes()
for method in ['sequence','em_sequence']:
 rows,diag=s.decode(z,h,method=method,iterations=2);assert np.isfinite(diag['logits']).all()
report={'em':results,'wrapper_parity':True,'c_sequence_and_combined_smoke':True,'acquisition_backend':a.backend_status(),'science_backends':s.backend_status(),'candidate_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'src/rescue').glob('*rust.so')}}
out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

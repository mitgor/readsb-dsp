"""Bit-exact pulse/bank parity, error partial-write contracts and packet guards."""
from pathlib import Path
import argparse,ctypes as C,json,time,statistics,hashlib,sys
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--loops',type=int,default=25);a=p.parse_args();D=a.root;power=np.load(D/'input/power.npy');model=json.loads((D/'input/model.json').read_text());weights=np.array(model['weights'],np.float64);bias=float(model['bias']);rng=np.random.default_rng(20261110);libs={};ptr=lambda x:x.ctypes.data_as(C.c_void_p)
for name in ['c','rust',*(['actual'] if (D/'build/actual.so').exists() else [])]:
 l=C.CDLL(str(D/'build'/(name+'.so')));l.rescue_pulse_discriminant.argtypes=[C.c_void_p,C.c_int64,C.c_void_p,C.c_int64,C.c_void_p,C.c_double,C.c_void_p,C.c_void_p];l.rescue_pulse_discriminant.restype=C.c_int;l.rescue_pulse_bank.argtypes=[C.c_void_p,C.c_int64,C.c_void_p,C.c_int64,C.c_void_p,C.c_void_p,C.c_int64,C.c_void_p,C.c_void_p];l.rescue_pulse_bank.restype=C.c_int;libs[name]=l

def run(lib,x,w=weights,b=bias,starts=None,count=None,length=None):
 x=np.ascontiguousarray(x,np.float32);w=np.ascontiguousarray(w,np.float64);n=len(x);starts=np.arange(n,dtype=np.int64)*482 if starts is None else np.array(starts,np.int64);count=n if count is None else count;length=x.size if length is None else length;l=np.full((max(n,len(starts)),112),91,np.float32);c=l.copy();rc=lib.rescue_pulse_discriminant(ptr(x),length,ptr(starts),count,ptr(w),b,ptr(l),ptr(c));return rc,l,c

def bank(lib,x,w,b,models=None):
 x=np.ascontiguousarray(x,np.float32);w=np.ascontiguousarray(w,np.float64);b=np.ascontiguousarray(b,np.float64);n=len(x);m=len(b);starts=np.arange(n,dtype=np.int64)*482;l=np.full((n,m,112),91,np.float32);c=l.copy();rc=lib.rescue_pulse_bank(ptr(x),x.size,ptr(starts),n,ptr(w),ptr(b),m if models is None else models,ptr(l),ptr(c));return rc,l,c

def exact(ref,out,label):
 assert ref[0]==out[0],(label,'return')
 for i,(x,y) in enumerate(zip(ref[1:],out[1:])):assert x.tobytes()==y.tobytes(),(label,i,int(np.count_nonzero(x!=y)),float(np.nanmax(np.abs(x-y))))
ref=run(libs['c'],power);assert ref[0]==0
for name,l in libs.items():exact(ref,run(l,power),('recorded',name))
checks=0
cases=[('zero',np.zeros((4,482),np.float32),weights,bias),('subnormal',np.full((4,482),1e-40,np.float32),weights,bias),('large',np.full((4,482),np.finfo(np.float32).max,np.float32),weights,bias),('overflow',power[:2],np.full(8,1e308),1e308)]
for i in range(32):cases.append(('random-'+str(i),rng.random((8,482),dtype=np.float32)*10**rng.uniform(-8,6),rng.normal(size=8),float(rng.normal())))
for label,x,w,b in cases:
 r=run(libs['c'],x,w,b)
 for name,l in libs.items():exact(r,run(l,x,w,b),(label,name))
 checks+=1
# Invalid values at preamble/early/late bit positions must preserve partial writes.
for at in [0,30,41,200,481]:
 for value in [-1,np.nan,np.inf]:
  x=power[:2].copy();x[1,at]=value;r=run(libs['c'],x)
  for name,l in libs.items():exact(r,run(l,x),('invalid',at,str(value),name))
  checks+=1
for kwargs in [dict(length=481),dict(count=-1),dict(starts=[-1]),dict(starts=[1],length=482),dict(count=0),dict(w=np.full(8,np.nan)),dict(b=np.inf)]:
 r=run(libs['c'],power[:1],**kwargs)
 for name,l in libs.items():exact(r,run(l,power[:1],**kwargs),('bounds',str(kwargs),name))
 checks+=1
bank_tests=0
for models in [1,2,4,8]:
 w=np.tile(weights,(models,1))*np.linspace(.5,2,models)[:,None];b=np.linspace(-1,1,models);r=bank(libs['c'],power[:64],w,b)
 for name,l in libs.items():exact(r,bank(l,power[:64],w,b),('bank',models,name))
 for j in range(models):
  scalar=run(libs['c'],power[:64],w[j],b[j]);assert scalar[1].tobytes()==r[1][:,j].tobytes() and scalar[2].tobytes()==r[2][:,j].tobytes()
 bank_tests+=1
for models in [0,9]:
 r=bank(libs['c'],power[:2],np.tile(weights,(8,1)),np.zeros(8),models)
 for name,l in libs.items():exact(r,bank(l,power[:2],np.tile(weights,(8,1)),np.zeros(8),models),('bank-bounds',models,name))
 bank_tests+=1
# Packet recovery through unchanged production hard/weak-bit CRC logic.
from rescue.pipeline_v3 import BackendV3
from rescue.dsp import payloads,crc_batch
backend=BackendV3();signatures={}
for name,lib in libs.items():
 r=run(lib,power);pred=payloads(r[1]);fixed,_=backend.soft_decode(r[1],r[2]);repairs={}
 for index,row,bits in fixed:pred[index]=row;repairs[int(index)]=list(map(int,bits))
 valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17);signatures[name]=[(int(i),pred[i].tobytes().hex(),repairs.get(int(i),[])) for i in np.flatnonzero(valid)]
assert all(v==signatures['c'] for v in signatures.values())
for l in libs.values():run(l,power)
trials=[];names=list(libs)
for trial in range(9):
 times={}
 for name in names[trial%len(names):]+names[:trial%len(names)]:
  mark=time.process_time()
  for i in range(a.loops):out=run(libs[name],power)
  times[name]=(time.process_time()-mark)/a.loops;exact(ref,out,('timing',name))
 trials.append(dict(trial=trial,cpu_s=times));print(trials[-1],flush=True)
result=dict(windows=len(power),all_arrays_bit_exact=True,error_and_numeric_controls=checks,bank_controls=bank_tests,packet_window_outputs=len(signatures['c']),packet_signature_sha256=hashlib.sha256(json.dumps(signatures['c']).encode()).hexdigest(),trials=trials,median_cpu_s={k:statistics.median(t['cpu_s'][k] for t in trials) for k in names},median_saving_vs_C_percent=statistics.median(100*(1-t['cpu_s']['rust']/t['cpu_s']['c']) for t in trials),libraries={k:hashlib.sha256((D/'build'/(k+'.so')).read_bytes()).hexdigest() for k in names},fixture_sha256=hashlib.sha256((D/'input/power.npy').read_bytes()).hexdigest(),production_changed=False,scope='Scalar and1-8-model bank, same ordered FP64 accumulation/FP32 outputs, partial error writes and unchanged packet guards. Window outputs are not unique additions beyond full pipeline.')
(D/'benchmark.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='trials'},indent=2))

"""Exact score/selector parity, ties/edges/budgets and downstream noise controls."""
import argparse,ctypes as C,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--decoder-root',type=Path,default=ROOT);a=p.parse_args();w=a.work.resolve();libs={}
for name in ['c','rust']:
 l=C.CDLL(str(w/(name+'.so')));l.rescue_extended_scores_neon.argtypes=[C.c_void_p,C.c_int64,C.c_double,C.c_double,C.c_double,C.c_void_p];l.rescue_extended_scores_neon.restype=C.c_int;l.rescue_extended_select_neon.argtypes=[C.c_void_p,C.c_int64,C.c_int64,C.c_double,C.c_double,C.c_double,C.c_int,C.c_void_p,C.c_void_p];l.rescue_extended_select_neon.restype=C.c_int64;libs[name]=l
weights=(.6538461446762085,-.3461538553237915,11.769231796264648);rng=np.random.default_rng(20261029);fallback=0;selected=0

def call(name,p,core,budget):
 ids=np.full(budget,-777,np.int64);values=np.full(budget,np.nan,np.float64);code=libs[name].rescue_extended_select_neon(p.ctypes.data,len(p),core,*weights,budget,ids.ctypes.data,values.ctypes.data);return code,ids,values

def check(p,core,budget):
 before=p.copy();out={}
 for name in libs:
  scores=np.full(max(1,len(p)-51),np.nan,np.float64);code=libs[name].rescue_extended_scores_neon(p.ctypes.data,len(p),*weights,scores.ctypes.data);out[name]=(code,scores.copy(),call(name,p,core,budget));assert np.array_equal(before,p)
 x,y=out['c'],out['rust'];assert x[0]==y[0];assert x[1].tobytes()==y[1].tobytes(),'scorer rounding mismatch';a,b=x[2],y[2];assert a[0]==b[0] and a[1].tobytes()==b[1].tobytes() and a[2].tobytes()==b[2].tobytes(),'candidate mismatch';return a
for test in range(1200):
 n=[52,53,54,55,56,57,488,489,490,491,512,2048,4096][test%13];p=rng.exponential(1,size=n).astype(np.float32)
 if test%7==0:p.fill(0)
 if test%11==0:p.fill(1)
 budget=[1,8,16,64,256][test%5];core=[0,n//2,n,n+50][test%4];code,ids,values=check(p,core,budget);fallback+=code==-2;selected+=max(code,0)
# Repeated exact binary templates must preserve the upstream SciPy fallback.
p=np.zeros(2048,np.float32);on=[0,1,4,5,14,15,18,19,32,33,38,39,42,43,46,47,48,49]
for start in [80,1080]:p[start+np.asarray(on)]=1
assert check(p,len(p),16)[0]==-2,'Missing equal-score fallback';fallback+=1
# Invalid arguments are rejected before dereferencing the indicated nulls.
for name,l in libs.items():
 for n,core,budget in [(51,0,16),(10000052,0,16),(100,-1,16),(100,100,0),(100,100,257)]:assert l.rescue_extended_select_neon(None,n,core,*weights,budget,None,None)==-1
# Noise acquisition may legitimately emit hypotheses; none may be called a
# recovered packet until it passes the same frozen coherent decoder/CRC guards.
sys.path.insert(0,str(a.decoder_root/'src'));from rescue.coherent_fast import native_windows
noise_candidates=0;noise_valid=0
for test in range(64):
 iq=(rng.normal(0,.01,8192)+1j*rng.normal(0,.01,8192)).astype(np.complex64);p=(iq.real*iq.real+iq.imag*iq.imag).astype(np.float32);code,ids,score=check(p,len(p),16)
 if code>=0 and code:
  noise_candidates+=code;valid=native_windows(iq,ids[:code])[-1];noise_valid+=int(valid.sum())
assert noise_valid==0,'Frozen decoder accepted a noise hypothesis; quarantine and inspect'
result={'exact_scoring_and_candidate_cases':1201,'budgets':[1,8,16,64,256],'fallback_cases':fallback,'selected_candidates_in_non_noise_cases':selected,'invalid_argument_checks':10,'input_immutable':True,'noise_blocks':64,'noise_candidate_hypotheses':noise_candidates,'noise_crc_valid':noise_valid,'noise_policy':'Acquisition hypotheses are not accepted packets; frozen installed coherent decoder used only in this offline process.'};a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

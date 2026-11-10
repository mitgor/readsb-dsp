"""Known synthetic repair/trust controls; no RF labels are inferred."""
import argparse,ctypes,json,subprocess
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--native',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture-dir',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.fixture_dir.mkdir(exist_ok=True)
class Event(ctypes.Structure):_fields_=[('ticks',ctypes.c_int64),('message',ctypes.c_uint8*14)]
lib=ctypes.CDLL(str(a.native.resolve()));lib.stream1090_native_decode.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int64,ctypes.POINTER(Event),ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)];lib.stream1090_native_decode.restype=ctypes.c_int
truth=bytes.fromhex('8d40621d58c382d690c8ac2863a7');N=2401200

def waveform(items):
 z=np.full((N,2),128,np.uint8)
 for start,msg in items:
  at=np.arange(start-4,start+300);t=(at-start)/2.4;on=((t>=0)&(t<.5))|((t>=1)&(t<1.5))|((t>=3.5)&(t<4))|((t>=4.5)&(t<5));bits=np.clip(np.floor(t-8).astype(int),0,111);values=np.unpackbits(np.frombuffer(msg,np.uint8))[bits];on|=(t>=8)&(t<120)&np.where(values!=0,(t-8-bits)<.5,(t-8-bits)>=.5);z[at[on],0]=210
 return z.tobytes()
def corrupt(bits):
 m=bytearray(truth)
 for b in bits:m[b//8]^=1<<(7-b%8)
 return bytes(m)
def native(raw,cap=16384):
 out=(Event*cap)();n=ctypes.c_uint32(99);rc=lib.stream1090_native_decode(raw,N,0,out,cap,ctypes.byref(n));return rc,[(out[i].ticks,bytes(out[i].message).hex()) for i in range(n.value)],n.value
patterns={'single':[70],'adjacent':[70,71],'three_burst':[70,71,72],'df19':[3]};report={}
for name,bits in patterns.items():
 for trust in [False,True]:
  items=([(240000,truth),(720000,truth)] if trust else [])+[(1200000,corrupt(bits)),(1920000,corrupt(bits))]
  raw=waveform(items);rc,rows,n=native(raw);assert rc==0
  r=subprocess.run([str(a.binary),'-s','2.4','-u','8'],input=raw,capture_output=True,check=True,timeout=30);old=[]
  for l in r.stdout.splitlines():
   if l.endswith(b';') and l[:1] in (b'<',b'@'):
    m=(l[15:-1] if l[:1]==b'<' else l[13:-1]).decode().lower()
    if len(m)==28 and int(m[:2],16)>>3==17:old.append((int(l[1:13],16),m))
  assert rows==old,(name,trust,rows,old)
  assert all(m==truth.hex() for _,m in rows),'Unexplained synthetic output'
  if trust:assert n>=3,(name,'repair not exercised')
  else:assert n==0,(name,'repair seeded trust')
  report[name+('_trusted' if trust else '_untrusted')]={'native':n,'executable':len(old),'packet_and_timestamp_exact':True,'known_payload_only':True}
raw=waveform([(240000,truth),(720000,truth),(1200000,truth),(1920000,truth)])
(a.fixture_dir/'clean.uc8').write_bytes(raw);rc,rows,n=native(raw,1);assert rc==-2 and n==0
count=ctypes.c_uint32(9);assert lib.stream1090_native_decode(None,0,0,None,0,ctypes.byref(count))==-1 and count.value==0
report['api']={'overflow_rejects_all_output':True,'invalid_arguments_rejected':True,'call_state_isolation':True}
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

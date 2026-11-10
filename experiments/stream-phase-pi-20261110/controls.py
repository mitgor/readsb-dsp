from pathlib import Path
import argparse,ctypes,subprocess,json,numpy as np
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
class Event(ctypes.Structure):_fields_=[('ticks',ctypes.c_int64),('message',ctypes.c_uint8*14)]
lib=ctypes.CDLL(str(a.native.resolve()));lib.phase_scan.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int64,ctypes.c_int64,ctypes.POINTER(Event),ctypes.c_uint32];lib.phase_scan.restype=ctypes.c_uint32;buffer=(Event*16384)();truth=bytes.fromhex('8d40621d58c382d690c8ac2863a7');N=2401200;clean=np.full((N,2),128,np.uint8)
for start in [240000,1200000,1920000]:
 at=np.arange(start-4,start+300);t=(at-start)/2.4;on=((t>=0)&(t<.5))|((t>=1)&(t<1.5))|((t>=3.5)&(t<4))|((t>=4.5)&(t<5));bits=np.clip(np.floor(t-8).astype(int),0,111);values=np.unpackbits(np.frombuffer(truth,np.uint8))[bits];on|=(t>=8)&(t<120)&np.where(values!=0,(t-8-bits)<.5,(t-8-bits)>=.5);clean[at[on],0]=210
noise=np.clip(np.random.default_rng(101110).normal(127.5,8,(N,2)),0,255).astype(np.uint8);report={}
for name,z in [('clean',clean),('noise',noise)]:
 raw=z.tobytes();n=lib.phase_scan(ctypes.cast(ctypes.c_char_p(raw),ctypes.c_void_p),N,0,0,buffer,len(buffer));assert n<=len(buffer);native=[bytes(buffer[i].message).hex() for i in range(n)];r=subprocess.run([str(a.binary),'-s','2.4','-u','8'],input=raw,capture_output=True,check=True,timeout=30);old=[]
 for line in r.stdout.splitlines():
  if line.endswith(b';') and line[:1] in (b'<',b'@'):
   msg=(line[15:-1] if line[:1]==b'<' else line[13:-1]).decode().lower()
   if len(msg)==28 and int(msg[:2],16)>>3==17:old.append(msg)
 if name=='clean':assert truth.hex() in native and truth.hex() in old;assert set(native)==set(old)=={truth.hex()}
 report[name]={'native_raw_df17':len(native),'executable_raw_df17':len(old),'known_clean_payload_only':name=='clean','noise_has_no_stock_identity':name=='noise','accepted_noise_with_empty_identity':0 if name=='noise' else None}
a.output.write_text(json.dumps(report,indent=2));print(json.dumps(report))

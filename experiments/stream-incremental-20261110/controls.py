"""Known RF, arbitrary splits, trust/repair and fail-closed session controls."""
import argparse,ctypes,json,hashlib
from pathlib import Path
import numpy as np
from bindings import Decoder,Event
p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--incremental',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture-dir',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.fixture_dir.mkdir(exist_ok=True);d=Decoder(a.batch,a.incremental);N=2401200;truth=bytes.fromhex('8d40621d58c382d690c8ac2863a7')
def wave(items):
 z=np.full((N,2),128,np.uint8)
 for at,msg in items:
  ix=np.arange(at-4,at+300);t=(ix-at)/2.4;on=((t>=0)&(t<.5))|((t>=1)&(t<1.5))|((t>=3.5)&(t<4))|((t>=4.5)&(t<5));bits=np.clip(np.floor(t-8).astype(int),0,111);v=np.unpackbits(np.frombuffer(msg,np.uint8))[bits];on|=(t>=8)&(t<120)&np.where(v!=0,(t-8-bits)<.5,(t-8-bits)>=.5);z[ix[on],0]=210
 return z.tobytes()
m=bytearray(truth);m[8]^=2;broken=bytes(m)
fixtures={'boundary_clean':wave([(240000,truth),(479940,truth),(1199940,truth),(2400450,truth)]),'trusted_repair':wave([(240000,truth),(479940,truth),(1199940,broken),(1919940,broken)]),'untrusted_repair':wave([(240000,broken),(479940,broken),(1199940,broken)]),'noise':np.clip(np.random.default_rng(111020).normal(127.5,8,(N,2)),0,255).astype(np.uint8).tobytes()};results={};sizes=[1,8207,8208,8209,47999,48000,120000,N]
# One-sample feeds are exercised on a short prefix plus an irregular sequence,
# avoiding millions of Python calls unrelated to the requested 20/50ms API.
for name,raw in fixtures.items():
 expected=d.whole(raw,0);assert all(m==truth.hex() for _,m in expected),name
 if name in ['noise','untrusted_repair']:assert not expected,name
 else:assert len(expected)>=3,name
 for size in sizes[1:]:
  ctx=d.begin(0,N);out=[]
  try:
   for at in range(0,N,size):out+=d.feed(ctx,raw[2*at:2*(at+size)],at)
   out+=d.finish(ctx);assert out==expected,(name,size)
  finally:d.close(ctx)
 ctx=d.begin(0,N);out=[];at=0;rng=np.random.default_rng(28010)
 try:
  while at<N:
   step=1 if at<30 else int(rng.integers(1,120001));step=min(step,N-at);out+=d.feed(ctx,raw[2*at:2*(at+step)],at);at+=step
  out+=d.finish(ctx);assert out==expected,(name,'random split')
 finally:d.close(ctx)
 results[name]={'packets':len(expected),'all_split_packet_timestamps_order_exact':True,'known_payload_only':True}
raw=fixtures['boundary_clean'];(a.fixture_dir/'boundary.uc8').write_bytes(raw);buf=(Event*16384)();n=ctypes.c_uint32(77)
# Gap and overlap reject and poison. No subsequent output is admitted.
for delta in [-1,1]:
 ctx=d.begin(0,N);d.feed(ctx,raw[:96000],0);rc=d.inc.stream1090_incremental_feed(ctx,raw[96000:192000],48000,48000+delta,buf,len(buf),ctypes.byref(n),0);assert rc==-5 and n.value==0
 rc=d.inc.stream1090_incremental_finish(ctx,buf,len(buf),ctypes.byref(n),0);assert rc==-5 and n.value==0;d.close(ctx)
ctx=d.begin(0,N);rc=d.inc.stream1090_incremental_finish(ctx,buf,len(buf),ctypes.byref(n),0);assert rc==-5 and n.value==0;d.close(ctx)
ctx=d.begin(0,N);rc=d.inc.stream1090_incremental_feed(ctx,raw,N,0,buf,1,ctypes.byref(n),0);assert rc==-2 and n.value==0;d.close(ctx)
ctx=d.begin(0,N);rc=d.inc.stream1090_incremental_feed(ctx,raw,N,0,buf,len(buf),ctypes.byref(n),1);assert rc==-4 and n.value==0;d.close(ctx)
ctx=d.begin(0,N);d.feed(ctx,raw,0);d.finish(ctx);rc=d.inc.stream1090_incremental_finish(ctx,buf,len(buf),ctypes.byref(n),0);assert rc==-5 and n.value==0;d.close(ctx)
assert not d.inc.stream1090_incremental_create(-1,N) and not d.inc.stream1090_incremental_create(0,4802401)
results['api']={'gap_overlap_rejected':True,'incomplete_finish_rejected':True,'overflow_rejects_partial_output':True,'deadline_rejects_partial_output':True,'closed_context_rejected':True,'contexts_isolated':True,'input_bounds_rejected':True};a.output.write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results))

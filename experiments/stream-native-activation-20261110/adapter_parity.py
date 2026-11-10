"""Current live per-window adapter parity, fallbacks and deadline controls."""
from pathlib import Path
import argparse,sys,types,importlib.util,json,hashlib,time,ctypes
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--original',type=Path,required=True);p.add_argument('--original-helper',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--work',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.work.mkdir(exist_ok=True)
# Only the public constants are needed from the production worker module.
pkg=types.ModuleType('rescue');pkg.__path__=[str(a.source)];sys.modules['rescue']=pkg
st=types.ModuleType('rescue.streaming');st.CORE=2400000;st.HALO=600;st.TOTAL=2401200;sys.modules[st.__name__]=st
# Load the original helper with unused research dependencies stubbed. Its exact
# CRC/parse/compare function source is preserved independently, not replaced.
s=a.original_helper.read_text();start=s.index('def valid_df17');end=s.index('\ndef classify_incremental',start)
h=types.ModuleType('rescue.stream1090_shadow');exec('import bisect,statistics\nfrom collections import defaultdict\n'+s[start:end],h.__dict__);sys.modules[h.__name__]=h
spec=importlib.util.spec_from_file_location('rescue.original',a.original);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
from rescue.stream1090_method import Stream1090Method,Event
cfg=a.work/'backend.json';cfg.write_text(json.dumps({'backend':'native','library':str(a.library.resolve()),'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest()}));new=Stream1090Method(a.binary,timeout_s=3,backend_config=cfg,fallback_marker=a.work/'fallback.json');legacy=old.Stream1090Method(a.binary,timeout_s=3)
cases=[c for c in json.loads((a.prepared/'cases.json').read_text()) if c['family']=='long' and c['reference_coverage_complete']];refs=json.loads((a.prepared/'references.json').read_text())['long']['stock'];frames=[dict(ticks=r['ticks']-2398,message_hex=r['message_hex']) for r in refs];cpu={'native':0.,'executable':0.};allrows=[]
with (a.prepared/'rf.bin').open('rb') as f:
 for i,c in enumerate(cases):
  f.seek(c['byte_offset']);raw=f.read(c['bytes']);assert hashlib.sha256(raw).hexdigest()==c['sha256'];nr,ncpu=new.decode(raw,c['first_sample'],frames);er,ecpu=legacy.decode(raw,c['first_sample'],frames)
  assert nr==er,(c['id'],len(nr),len(er));assert new.last_alignment==legacy.last_alignment,(c['id'],'alignment');assert new.backend=='native' and not new.native_error
  allrows.extend((c['id'],r['ticks'],r['message_hex']) for r in nr);cpu['native']+=ncpu;cpu['executable']+=ecpu
  if i%25==0:print('Paired adapter windows',i+1,flush=True)
# Native failure must replay the SAME bytes through the original executable.
class Broken:
 def stream1090_native_decode_timeout_us(self,*args):return -4
new.library=Broken();new.config_key=None
nr,_=new.decode(raw,c['first_sample'],frames);er,_=legacy.decode(raw,c['first_sample'],frames);assert nr==er and new.backend=='executable' and new.count['same_window_fallbacks']==1
prior=new.count['native_calls'];new.decode(raw,c['first_sample'],frames);assert new.count['native_calls']==prior,'Failed native backend retried'
# Bounded ABI must reject all output after a deliberately tiny deadline.
lib=ctypes.CDLL(str(a.library.resolve()));fn=lib.stream1090_native_decode_timeout_us;fn.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int64,ctypes.POINTER(Event),ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_uint32];fn.restype=ctypes.c_int
n=ctypes.c_uint32(99);events=(Event*16384)();rc=fn(raw,st.TOTAL,c['first_sample'],events,len(events),ctypes.byref(n),1);assert rc==-4 and n.value==0
# Digest mismatch is fail-closed and falls back before executing native code.
badcfg=a.work/'bad.json';badcfg.write_text(json.dumps({'backend':'native','library':str(a.library.resolve()),'library_sha256':'0'*64}));bad=Stream1090Method(a.binary,3,badcfg,a.work/'bad-fallback.json');br,_=bad.decode(raw,c['first_sample'],frames);assert br==er and bad.count['native_calls']==0
result={'windows':len(cases),'exact_rows_and_alignment':True,'extras_before_common_coordinator_guard':len(allrows),'packet_timestamp_sha256':hashlib.sha256(json.dumps(allrows).encode()).hexdigest(),'same_window_deadline_fallback_exact':True,'failed_native_not_retried':True,'native_deadline_output_rejected':True,'checksum_failure_fallback_exact':True,'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest(),'cpu_s':cpu,'cpu_scope':'Native includes thread+conversion; legacy recorded child only, not a like-for-like performance result'}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

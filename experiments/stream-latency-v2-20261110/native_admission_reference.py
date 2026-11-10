"""Single-owner, bounded stock indexes and unchanged production guards in Rust.

No sockets, models, SDR, production configuration or wall-clock access. Callers
append only stock frames that have arrived, in arrival order. Lowercase DF17
payloads are the production wire contract. Outputs preserve original row dicts.
"""
import ctypes as C
import math
from pathlib import Path
SOURCES=('energy','timing','soft','matched','coherent','sequence','acquisition','pulse','header','sic','neural','stream1090')
DECISIONS=('invalid','neural_duplicate_energy','duplicate_120us','no_prior_stock_icao','stock_conflict','alignment_unverified')+tuple('added_'+s for s in SOURCES)
class Row(C.Structure):
 _fields_=[('ticks',C.c_int64),('payload',C.c_uint8*14),('source',C.c_uint8),('format_valid',C.c_uint8)]
class Audit(C.Structure):
 _fields_=[('matches',C.c_uint64),('median_twice_ticks',C.c_int64),('verified',C.c_uint64)]
def row(frame,source=None):
 t=frame['ticks']
 if type(t) not in (int,float) or not math.isfinite(t) or t*4!=int(t*4) or not -(1<<63)<=t*4<(1<<63):raise ValueError('Expected exact quarter-tick timestamp')
 t=int(t*4)
 p=frame['message_hex'];valid=False;raw=bytes(14)
 if isinstance(p,str) and len(p)==28:
  if p!=p.lower():raise ValueError('Production payloads must be canonical lowercase')
  try:raw=bytes.fromhex(p);valid=len(raw)==14
  except ValueError:pass
 if not valid:raw=bytes(14)
 s=frame.get('source') if source is None else source
 code=SOURCES.index(s) if s in SOURCES else 255
 return Row(t,(C.c_uint8*14).from_buffer_copy(raw),code,int(valid))
class NativeAdmission:
 def __init__(self,library,maxlen=100000,epoch=0):
  self.lib=C.CDLL(str(Path(library)));self.epoch=epoch;self.handle=None
  specs=[('na_row_size',[],C.c_size_t),('na_audit_size',[],C.c_size_t),('na_new',[C.c_size_t,C.c_uint64],C.c_void_p),('na_free',[C.c_void_p],None),('na_reset',[C.c_void_p,C.c_uint64],C.c_int),('na_append',[C.c_void_p,C.c_uint64,C.POINTER(Row),C.c_size_t],C.c_int),('na_latest',[C.c_void_p,C.POINTER(C.c_int64)],C.c_int),('na_len',[C.c_void_p],C.c_size_t),('na_evaluate',[C.c_void_p,C.c_uint64,C.POINTER(Row),C.c_size_t,C.POINTER(C.c_uint32),C.c_size_t,C.POINTER(C.c_size_t),C.POINTER(Audit),C.POINTER(C.c_uint64),C.c_size_t],C.c_int)]
  for name,args,ret in specs:f=getattr(self.lib,name);f.argtypes=args;f.restype=ret
  assert self.lib.na_row_size()==C.sizeof(Row)==24 and self.lib.na_audit_size()==C.sizeof(Audit)==24
  self.handle=self.lib.na_new(maxlen,epoch)
  if not self.handle:raise ValueError('Stock capacity must be 1..1000000')
 def append_stock(self,frame):self.append_stocks([frame])
 def append_stocks(self,frames):
  rows=(Row*len(frames))(*(row(r,'energy') for r in frames));rc=self.lib.na_append(self.handle,self.epoch,rows,len(rows))
  if rc:raise ValueError('Native stock append failed: '+str(rc))
 def reset(self,epoch):
  assert self.lib.na_reset(self.handle,epoch)==0;self.epoch=epoch
 @property
 def latest_stock_tick(self):
  value=C.c_int64();rc=self.lib.na_latest(self.handle,C.byref(value));assert rc>=0;return value.value//4 if rc else None
 def __len__(self):return self.lib.na_len(self.handle)
 def evaluate(self,candidates,start,stop):
  # start/stop intentionally do not filter: production evaluate uses all supplied
  # anchors/candidates; the caller owns output core filtering.
  if len(candidates)>100000:raise ValueError('Candidate capacity exceeded')
  candidates=[r for r in candidates if r['source'] in SOURCES]
  rows=(Row*len(candidates))(*(row(r) for r in candidates));selected=(C.c_uint32*len(candidates))();n=C.c_size_t();audit=Audit();counts=(C.c_uint64*18)()
  rc=self.lib.na_evaluate(self.handle,self.epoch,rows,len(rows),selected,len(selected),C.byref(n),C.byref(audit),counts,len(counts))
  if rc:raise ValueError('Native admission failed: '+str(rc))
  out=[candidates[selected[i]] for i in range(n.value)];report=dict(matches=int(audit.matches),median_abs_error_us=None if audit.median_twice_ticks<0 else audit.median_twice_ticks/96,verified=bool(audit.verified))
  decisions={name:int(v) for name,v in zip(DECISIONS,counts) if v}
  if not report['verified']:decisions={'alignment_unverified':int(counts[5])}
  return out,report,decisions
 def close(self):
  if self.handle:self.lib.na_free(self.handle);self.handle=None
 def __enter__(self):return self
 def __exit__(self,*_):self.close()

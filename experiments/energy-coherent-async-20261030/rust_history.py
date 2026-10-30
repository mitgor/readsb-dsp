"""ctypes ownership wrapper; all access serialized before the shared emitter."""
import ctypes as c,math,threading
from collections import Counter
class RustHistory:
 names=('ttl_expired','capacity_evictions','epoch_resets','wrong_epoch_rejected','unvalidated_rejected','stale_or_unanchored_extra_rejected','cross_stream_duplicate_rejected','late_stock_after_extra_race','stock_same_event_preserved','emitted_stock','emitted_energy','emitted_coherent')
 def __init__(self,path,ttl=5.,tolerance_ticks=1440,capacity=100000):
  self.lib=c.CDLL(str(path));self.lock=threading.Lock();self.ttl=ttl;self.tol=tolerance_ticks;self.capacity=capacity
  signatures=dict(ec_new=([c.c_uint64,c.c_int64,c.c_size_t],c.c_void_p),ec_free=([c.c_void_p],None),ec_reset=([c.c_void_p,c.c_uint64],None),ec_prune=([c.c_void_p,c.c_uint64],None),ec_push=([c.c_void_p,c.c_uint8,c.c_uint64,c.c_int64,c.c_void_p,c.c_uint64,c.c_bool],c.c_int),ec_count=([c.c_void_p,c.c_size_t],c.c_uint64),ec_len=([c.c_void_p],c.c_size_t))
  for name,(args,restype) in signatures.items():f=getattr(self.lib,name);f.argtypes=args;f.restype=restype
  self.handle=self.lib.ec_new(self.ns(ttl),tolerance_ticks,capacity)
  if not self.handle:raise ValueError('Invalid bounded history configuration')
 def ns(self,seconds):
  if not math.isfinite(seconds) or seconds<0 or seconds>18446744073:raise ValueError('Invalid monotonic seconds')
  return round(seconds*1e9)
 def push(self,source,epoch,ticks,payload,now,*,validated=False):
  if source not in ('stock','energy','coherent'):raise ValueError('Two-method experiment only')
  if not 0<=epoch<2**64 or not -2**63<=ticks<2**63:raise ValueError('Epoch/ticks out of range')
  p=bytes.fromhex(payload)
  if len(p)!=14:raise ValueError('Expected complete DF17 payload')
  with self.lock:
   if not self.handle:raise RuntimeError('History closed')
   result=self.lib.ec_push(self.handle,('stock','energy','coherent').index(source),epoch,ticks,p,self.ns(now),validated)
   if result<0:raise RuntimeError('Native dedup input error')
   return bool(result)
 def prune(self,now):
  with self.lock:self.lib.ec_prune(self.handle,self.ns(now))
 def reset(self,epoch):
  if not 0<=epoch<2**64:raise ValueError('Epoch out of range')
  with self.lock:self.lib.ec_reset(self.handle,epoch)
 @property
 def count(self):
  with self.lock:return Counter({name:self.lib.ec_count(self.handle,i) for i,name in enumerate(self.names) if self.lib.ec_count(self.handle,i)})
 @property
 def size(self):
  with self.lock:return self.lib.ec_len(self.handle)
 def close(self):
  with self.lock:
   if self.handle:self.lib.ec_free(self.handle);self.handle=None

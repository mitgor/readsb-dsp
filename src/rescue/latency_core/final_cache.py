"""One Rust transmission history, anonymous socketpair, bounded RAM-only sink."""
import ctypes as C,collections,hashlib,json,socket,threading,time

class RustCache:
 def __init__(self,path,epoch):
  self.lib=C.CDLL(str(path));self.epoch=epoch
  for name,args,ret in [('ec_new',[C.c_uint64,C.c_int64,C.c_size_t],C.c_void_p),('ec_free',[C.c_void_p],None),('ec_reset',[C.c_void_p,C.c_uint64],None),('ec_push',[C.c_void_p,C.c_uint8,C.c_uint64,C.c_int64,C.c_void_p,C.c_uint64,C.c_bool],C.c_int),('ec_count',[C.c_void_p,C.c_size_t],C.c_uint64)]:
   f=getattr(self.lib,name);f.argtypes=args;f.restype=ret
  self.h=self.lib.ec_new(5000000000,1440,100000);assert self.h;self.lib.ec_reset(self.h,epoch)
 def push(self,source,t,p,now,validated=True):
  assert now>=0;v=self.lib.ec_push(self.h,source,self.epoch,t,bytes.fromhex(p),round(now*1e9),validated);assert v>=0;return bool(v)
 def counts(self):return {k:int(self.lib.ec_count(self.h,i)) for i,k in enumerate(['ttl_expired','capacity_evictions','epoch_resets','wrong_epoch','unvalidated','stale','duplicates','late_stock_after_extra_race','stock_duplicate_preserved','stock_emitted','stream1090_emitted','energy_emitted'])}
 def close(self):
  if self.h:self.lib.ec_free(self.h);self.h=None

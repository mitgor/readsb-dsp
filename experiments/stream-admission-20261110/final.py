"""One Rust transmission history, anonymous socketpair, bounded RAM-only sink."""
import ctypes as C,collections,hashlib,json,socket,threading,time
from rescue.feed import beast,CORRECTION,valid
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
class Final:
 def __init__(self,library,epoch):
  self.cache=RustCache(library,epoch);self.tx,self.rx=socket.socketpair();self.tx.settimeout(2);self.rx.settimeout(None);self.queue=collections.deque();self.lock=threading.Lock();self.records=[];self.expected_stock=hashlib.sha256();self.actual_stock=hashlib.sha256();self.error=None;self.total=0;self.count=collections.Counter();self.thread=threading.Thread(target=self.receive);self.thread.start();self.rf_origin=None;self.rf_first=None;self.history=None;self.stock_watermark=None
 def receive(self):
  pending=bytearray()
  try:
   while True:
    raw=self.rx.recv(65536)
    if not raw:break
    pending.extend(raw)
    while True:
     with self.lock:item=self.queue[0] if self.queue else None
     if item is None or len(pending)<len(item[0]):break
     wire,meta=item;assert bytes(pending[:len(wire)])==wire;del pending[:len(wire)]
     with self.lock:self.queue.popleft()
     meta=dict(meta,received=time.monotonic());self.records.append(meta)
     if meta['source']=='stock':self.actual_stock.update(wire)
   assert not pending and not self.queue,'Truncated local sink'
  except BaseException as e:self.error=repr(e)
 def write(self,wire,meta):
  self.total+=len(wire);assert self.total<=16*1048576,'RAM output cap'
  with self.lock:self.queue.append((wire,meta))
  self.tx.sendall(wire)
 def stock(self,r,now,timed=True):
  wire=b'\x1a3'+(int(r['ticks_12mhz']).to_bytes(6,'big')+bytes([r['signal_byte']])+bytes.fromhex(r['message_hex'])).replace(b'\x1a',b'\x1a\x1a')
  assert self.cache.push(0,r['ticks'],r['message_hex'],now);self.stock_watermark=r['ticks'] if self.stock_watermark is None else max(self.stock_watermark,r['ticks']);self.expected_stock.update(wire)
  self.write(wire,dict(source='stock',ticks=r['ticks'],message_hex=r['message_hex'],scheduled=r['arrival'],timed=timed))
 def extra(self,r,audit,elapsed,lane):
  assert r['source'] in ['stream1090','energy'] and valid(r['message_hex'])
  assert audit['verified'] and audit['matches']>=20 and audit['median_abs_error_us']<=2
  t=r['ticks'];p=r['message_hex'];frames=self.history.snapshot();ids=frames.identities.get(p[2:8],())
  if not any(t-360000000<=s<=t for s,q in ids):self.count['relay_no_prior_stock']+=1;return
  if any(abs(s-t)<=48 and q!=p for s,q in ids):self.count['relay_stock_conflict']+=1;return
  watermark=self.stock_watermark
  if watermark is None or not 0<=watermark-t<=36000000:self.count['relay_RF_age_rejected']+=1;return
  if self.cache.push(1 if r['source']=='stream1090' else 2,t,p,100+elapsed):
   self.count['emitted_'+lane]+=1
   self.write(beast(p,t+CORRECTION),dict(r,lane=lane,admitted=elapsed,timed=True))
 def close(self):
  self.tx.shutdown(socket.SHUT_WR);self.thread.join(timeout=3);assert not self.thread.is_alive();assert self.error is None,self.error;assert self.expected_stock.digest()==self.actual_stock.digest();result=self.cache.counts();self.cache.close();self.tx.close();self.rx.close();return result

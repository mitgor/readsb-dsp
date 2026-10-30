"""Experimental single-emitter, stock-preserving five-second dedup history.
No sleep, packet aggregation or timestamp rewriting. Caller supplies the existing
validation/epoch/alignment/conflict gates; this is not a replacement for them.
"""
from collections import Counter,deque

class HistoryMerge:
 def __init__(self,ttl=5.0,tolerance_ticks=1440,capacity=100000):
  self.ttl=ttl;self.tol=tolerance_ticks;self.capacity=capacity;self.index={};self.expiry=deque();self.serial=0;self.epoch=None;self.latest_stock=None;self.count=Counter()
 def prune(self,now):
  while self.expiry and (self.expiry[0][0]<=now or self.serial_count>self.capacity):
   self.count['capacity_evictions' if self.serial_count>self.capacity else 'ttl_expired']+=1
   _,key,ident=self.expiry.popleft();bucket=self.index.get(key)
   if bucket and ident in bucket:
    del bucket[ident]
    if not bucket:del self.index[key]
 @property
 def serial_count(self):return len(self.expiry)
 def reset(self,epoch):
  self.index.clear();self.expiry.clear();self.epoch=epoch;self.latest_stock=None;self.count['epoch_resets']+=1
 def push(self,source,epoch,ticks,payload,now,*,validated=False):
  self.prune(now);stock=source=='stock'
  if stock and epoch!=self.epoch:self.reset(epoch)
  if epoch!=self.epoch:self.count['wrong_epoch_rejected']+=1;return False
  if not stock and not validated:self.count['unvalidated_rejected']+=1;return False
  if stock:self.latest_stock=max(self.latest_stock or ticks,ticks)
  elif self.latest_stock is None or self.latest_stock-ticks>self.ttl*12000000:self.count['stale_or_unanchored_extra_rejected']+=1;return False
  key=(epoch,payload,ticks//self.tol);matches=[]
  for q in (key[2]-1,key[2],key[2]+1):
   for value in self.index.get((epoch,payload,q),{}).values():
    if abs(value[0]-ticks)<=self.tol:matches.append(value)
  if matches:
   if not stock:self.count['cross_stream_duplicate_rejected']+=1;return False
   if any(v[1]!='stock' for v in matches):self.count['late_stock_after_extra_race']+=1
   # Every original stock frame survives, even when it exposes an earlier race.
   self.count['stock_same_event_preserved']+=1
  self.serial+=1;self.index.setdefault(key,{})[self.serial]=(ticks,source);self.expiry.append((now+self.ttl,key,self.serial));self.prune(now)
  self.count['emitted_'+source]+=1;return True

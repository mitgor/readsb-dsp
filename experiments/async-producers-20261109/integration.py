"""Isolated all-source completion adapter. No production service/file/socket ownership."""
import asyncio,math,time
from collections import Counter,deque
from pathlib import Path
from rescue.shadow import evaluate
from rescue.streaming import HALO,CORE
from rescue.feed import CORRECTION,beast
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'async-relay-20261030'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'latency-publication-20261030'))
from async_relay import SOURCES
from prototype import ImmediateRelay
from dedup import HistoryMerge

class SourceHub:
 """One serialized final emitter; independent bounded per-method queues."""
 def __init__(self,enabled,clock=None,sink=None,max_age=3):
  self.enabled=enabled;self.clock=clock or time.monotonic;self.sink=sink or (lambda wire,source,now:None);self.relay=ImmediateRelay(HistoryMerge,allowed_sources=SOURCES,max_extra_age=max_age);self.queues={s:asyncio.Queue(256) for s in SOURCES};self.tasks=[];self.count=Counter();self.epoch=None
 def start(self):self.tasks=[asyncio.create_task(self.worker(s)) for s in sorted(SOURCES)]
 def begin_epoch(self,epoch):
  # This comes from the original RSC1/mirror batch, not service PID or TCP count.
  if self.epoch!=epoch:
   self.epoch=epoch;self.relay.reset_source();self.relay.epoch=epoch;self.relay.cache.reset(epoch)
 def stock(self,wire,frame,epoch,now=None):
  if epoch!=self.epoch:self.count['wrong_stock_epoch']+=1;return
  now=self.clock() if now is None else now;self.relay.stock(wire,frame,now,epoch);self.sink(self.relay.ready(now),'stock',now)
 def submit(self,source,epoch,events,audit):
  if source not in SOURCES:self.count['forbidden_source']+=len(events);return False
  if epoch!=self.epoch:self.count['wrong_producer_epoch']+=len(events);return False
  if not(audit.get('verified') is True and type(audit.get('matches')) is int and audit['matches']>=20 and isinstance(audit.get('median_abs_error_us'),(int,float)) and math.isfinite(audit['median_abs_error_us']) and 0<=audit['median_abs_error_us']<=2):self.count['bad_alignment']+=len(events);return False
  if len(events)>256 or any(e.get('source')!=source for e in events):self.count['malformed_source_contract']+=1;return False
  try:self.queues[source].put_nowait((epoch,[dict(e) for e in events],dict(audit),self.clock()));return True
  except asyncio.QueueFull:self.count['queue_overflow_'+source]+=len(events);return False
 async def worker(self,source):
  while True:
   epoch,events,audit,created=await self.queues[source].get()
   try:
    if epoch!=self.epoch:self.count['old_queued_epoch']+=len(events);continue
    if not self.enabled.get(source,False):self.count['disabled_'+source]+=len(events);continue
    for at in range(0,len(events),8):
     now=self.clock();batch=dict(epoch=epoch,created_unix=created,alignment=audit,extra=events[at:at+8]);self.relay.batch(batch,now,now,self.enabled);raw=self.relay.ready(now)
     if raw:self.sink(raw,source,now)
     await asyncio.sleep(0)
   except (ValueError,TypeError,KeyError,OverflowError):self.count['malformed_'+source]+=len(events)
   finally:self.queues[source].task_done()
 async def settle(self):await asyncio.gather(*(q.join() for q in self.queues.values()))
 async def close(self):
  await self.settle()
  for t in self.tasks:t.cancel()
  await asyncio.gather(*self.tasks,return_exceptions=True)
 def report(self):
  self.relay.cache.prune(self.clock());return dict(counts=dict(self.count),relay=dict(self.relay.count),dedup=dict(self.relay.cache.count),cache_entries=len(self.relay.cache.expiry),history_s=5,stock_holdback_s=0)

class Admission:
 """Unchanged causal production admission; final cross-source dedup only in hub."""
 def __init__(self,hub,max_age=3):self.hub=hub;self.max_age=max_age;self.pending=deque();self.energy={};self.count=Counter();self.generation=0;self.epoch=hub.epoch
 def sync_epoch(self):
  if self.epoch!=self.hub.epoch:
   self.pending.clear();self.energy.clear();self.generation=0;self.epoch=self.hub.epoch;self.count['epoch_reset']+=1
 def offer(self,batch,rows,now):
  self.sync_epoch()
  if batch.epoch!=self.hub.epoch:self.count['old_epoch']+=len(rows);return
  start=max((batch.first+HALO)*5,(batch.first+batch.bounds[0]*120000)*5);end=min((batch.first+HALO+CORE)*5,(batch.first+batch.bounds[1]*120000)*5)
  events=[dict(r,ticks=batch.first*5+r['sample_4msps']*3) for r in rows if r['source'] in SOURCES]
  self._offer(batch.epoch,start,end,events,now)
 def offer_stream1090(self,epoch,first,rows,now):
  self.sync_epoch()
  if epoch!=self.hub.epoch:self.count['old_external_epoch']+=len(rows);return
  if any(r['source']!='stream1090' for r in rows):raise ValueError('External adapter is Stream1090 only')
  self._offer(epoch,(first+HALO)*5,(first+HALO+CORE)*5,[dict(r) for r in rows],now)
 def _offer(self,epoch,start,end,events,now):
  for r in events:
   if r['source']=='energy':self.energy[(r['ticks'],r['message_hex'])]=r;self.generation+=1
  if len(self.pending)>=512:self.count['pending_overflow']+=len(events);return
  self.pending.append((epoch,start,end,events,now,None))
 def drain(self,frames,watermark,now):
  self.sync_epoch()
  if watermark is None:return
  cutoff=min([watermark-12000000]+[p[2]-12000000 for p in self.pending]);self.energy={k:r for k,r in self.energy.items() if r['ticks']>=cutoff}
  if len(self.energy)>40000:self.count['anchor_cap_fail_closed']+=1;self.pending.clear();self.energy.clear();return
  token=(len(frames),watermark,self.generation);remaining=deque()
  for epoch,start,end,events,created,previous in self.pending:
   if epoch!=self.hub.epoch:self.count['old_pending_epoch']+=len(events);continue
   if now-created>self.max_age:self.count['expired_pending']+=len(events);continue
   if watermark<end or token==previous:remaining.append((epoch,start,end,events,created,token));continue
   anchors=[r for r in self.energy.values() if end-12000000<=r['ticks']<end];current=[r for r in events if start<=r['ticks']<end and self.hub.enabled.get(r['source'],False)]
   extras,audit,decisions=evaluate(frames,anchors+[r for r in current if r['source']!='energy'],start,end)
   if not audit['verified']:remaining.append((epoch,start,end,events,created,token));self.count['alignment_wait']+=1;continue
   self.count.update(decisions);groups={}
   for r in extras:
    if start<=r['ticks']<end:groups.setdefault(r['source'],[]).append(r)
   for source,rows in groups.items():
    for at in range(0,len(rows),256):self.hub.submit(source,epoch,rows[at:at+256],audit)
  self.pending=remaining

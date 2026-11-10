from collections import Counter,deque
from .shadow import evaluate
from .streaming import HALO,CORE
from .feed import ALLOWED
SOURCES=frozenset(ALLOWED)
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

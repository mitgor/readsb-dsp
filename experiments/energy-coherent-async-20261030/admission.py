"""Existing admission, independent completions; global dedup lives only in Rust."""
from collections import deque
from bridge import Bridge
from rescue.shadow import evaluate
class Admission(Bridge):
 def drain(self,frames,watermark,now,rf_now):
  if watermark is None:return []
  cutoff=min([watermark-12000000]+[p[1]-12000000 for p in self.pending]);self.energy={k:r for k,r in self.energy.items() if r['ticks']>=cutoff}
  if len(self.energy)>40000:self.count['anchor_cap_fail_closed']+=1;self.pending.clear();self.energy.clear();return []
  remaining=deque();out=[];token=(len(frames),watermark,self.energy_generation)
  for start,end,events,created,batch,previous in self.pending:
   if now-created>self.max_age:self.count['pending_expired']+=len(events);continue
   if watermark<end or token==previous:remaining.append((start,end,events,created,batch,token));continue
   anchors=[r for r in self.energy.values() if end-12000000<=r['ticks']<end];current=[r for r in events if start<=r['ticks']<end and self.enabled.get(r['source'],False)]
   extras,audit,decisions=evaluate(frames,anchors+[r for r in current if r['source']!='energy'],start,end)
   if not audit['verified']:remaining.append((start,end,events,created,batch,token));self.count['alignment_wait']+=1;continue
   self.count.update(decisions)
   for r in extras:
    if not start<=r['ticks']<end or not self.enabled.get(r['source'],False):continue
    age=(rf_now-r['ticks'])/12e6
    if not 0<=age<=self.max_age:self.count['age_rejected']+=1;continue
    out.append(dict(r,rf_age_s=age,emitted=now,epoch=batch.epoch,alignment=audit))
  self.pending=remaining;return out

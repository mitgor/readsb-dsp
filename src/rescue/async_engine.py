"""Independent native worker admission. Grouping remains statistics-only."""
import json,time,os
from collections import Counter
from .async_admission import Admission
from .feed import ALLOWED
SOURCES=frozenset(ALLOWED)
class Outbox:
 def __init__(self,path,enabled):self.path=path;self.enabled=enabled;self.epoch=None;self.serial=0;self.count=Counter()
 def submit(self,source,epoch,events,audit):
  if source not in SOURCES or epoch!=self.epoch or not self.enabled.get(source,False):return False
  self.path.mkdir(parents=True,exist_ok=True)
  if len(list(self.path.glob('*.json')))>=512:self.count['outbox_overflow']+=len(events);return False
  self.serial+=1;tmp=self.path/('async-'+str(os.getpid())+'.tmp');dest=self.path/f'async-{time.monotonic_ns()}-{self.serial}.json'
  tmp.write_text(json.dumps(dict(created_unix=time.time(),epoch=epoch,admission='production_guarded_v1',producer=source,alignment=audit,extra=events)));tmp.replace(dest);self.count['published_'+source]+=len(events);return True

class Engine:
 def __init__(self,live,path,enabled):
  self.live=live;self.hub=Outbox(path,enabled);self.admit=Admission(self.hub)
  self.frames=[];self.health={};self.last_tick=0;self.last_context=0;self.count=Counter()
 def begin(self,batch):
  if self.hub.epoch!=batch.epoch:
   self.hub.epoch=batch.epoch;self.admit.sync_epoch();self.count['epoch_changes']+=1
 def offer(self,batch,rows,work):
  if batch.epoch==self.hub.epoch:self.admit.offer(batch,rows,time.monotonic())
 def tick(self):
  now=time.monotonic()
  if now-self.last_tick<.005:return
  self.last_tick=now
  if now-self.last_context>=.1:
   self.frames,self.health=self.live.snapshot();self.last_context=now
  if time.time()-self.health.get('aircraft_unix',0)<=5:
   self.admit.drain(self.frames,max((f['ticks'] for f in self.frames),default=None),now)
 def report(self):
  return dict(enabled=True,independent_producers=True,stock_holdback_s=0,epoch=self.hub.epoch,
   counts=dict(self.count),published=dict(self.hub.count),admission=dict(self.admit.count),pending=len(self.admit.pending))

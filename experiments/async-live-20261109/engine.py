"""Independent live completion admission; RAM-only bounded producer outbox."""
import concurrent.futures,json,time,os
from collections import Counter
from .async_live_admission import Admission
from .stream1090_method import Stream1090Method
SOURCES=frozenset(('energy','timing','soft','matched','coherent','sequence','acquisition','header','sic','neural','pulse','stream1090'))
class Outbox:
 def __init__(self,path,enabled):self.path=path;self.enabled=enabled;self.epoch=None;self.serial=0;self.count=Counter()
 def submit(self,source,epoch,events,audit):
  if source not in SOURCES or epoch!=self.epoch or not self.enabled.get(source,False):return False
  self.path.mkdir(exist_ok=True)
  if len(list(self.path.glob('*.json')))>=512:self.count['outbox_overflow']+=len(events);return False
  self.serial+=1;tmp=self.path/('async-'+str(os.getpid())+'.tmp');dest=self.path/f'async-{time.monotonic_ns()}-{self.serial}.json'
  tmp.write_text(json.dumps(dict(created_unix=time.time(),epoch=epoch,admission='production_guarded_v1',producer=source,alignment=audit,extra=events)));tmp.replace(dest);self.count['published_'+source]+=len(events);return True
class Engine:
 def __init__(self,live,path,enabled,binary,metrics=None):
  self.live=live;self.hub=Outbox(path,enabled);self.admit=Admission(self.hub);self.stream=Stream1090Method(binary) if enabled.get('stream1090') else None;self.executor=concurrent.futures.ThreadPoolExecutor(max_workers=1);self.jobs={};self.rows={};self.count=Counter();self.last_tick=0;self.last_context=0;self.frames=[];self.health={};self.wall_time=0;self.waiting={};self.groups=[];self.metrics=metrics;self.stream_cpu_s=0.
 def begin(self,batch):
  if self.hub.epoch!=batch.epoch:
   self.hub.epoch=batch.epoch;self.admit.sync_epoch();self.rows.clear();self.count['epoch_changes']+=1
  if self.stream and batch.whole_raw is not None:
   key=(batch.epoch,batch.first)
   if len(self.jobs)+len(self.waiting)>=2:self.count['stream_queue_full']+=1;return
   self.waiting[key]=(batch.whole_raw,time.monotonic())
 def offer(self,batch,rows,work):
  if batch.epoch==self.hub.epoch:self.admit.offer(batch,rows,time.monotonic())
 def tick(self):
  now=time.monotonic()
  if now-self.last_tick<.005:return
  self.last_tick=now;started=time.monotonic()
  if now-self.last_context>=.1:self.frames,self.health=self.live.snapshot();self.last_context=now
  watermark=max((f['ticks'] for f in self.frames),default=None)
  for key,(raw,created) in list(self.waiting.items()):
   if key[0]!=self.hub.epoch or now-created>3:del self.waiting[key];self.count['stream_wait_expired']+=1;continue
   if watermark is not None and watermark>=(key[1]+600+2400000)*5:
    self.jobs[key]=(self.executor.submit(self.stream.decode,raw,key[1],self.frames),created);del self.waiting[key]
  for key,(future,created) in list(self.jobs.items()):
   if not future.done():continue
   rows,cpu=future.result();del self.jobs[key]
   self.stream_cpu_s+=cpu
   if self.metrics is not None:self.metrics.record_external('stream1090',cpu)
   if key[0]!=self.hub.epoch:self.count['old_stream_epoch']+=1;continue
   self.rows[key]=rows
   if now-created<=3:self.admit.offer_stream1090(key[0],key[1],rows,now)
   else:self.count['stream_expired']+=1
  while len(self.rows)>5:del self.rows[next(iter(self.rows))]
  if time.time()-self.health.get('aircraft_unix',0)<=5:
   self.admit.drain(self.frames,watermark,now)
  self.wall_time+=time.monotonic()-started
 def grouped(self,result):
  if result:self.groups.append(result)
  if not self.groups:return None
  item,events,work=self.groups[0];key=(item[0],item[1])
  if self.stream and key not in self.rows and (key in self.jobs or key in self.waiting) and time.monotonic()-item[4]<5:return None
  return self.groups.pop(0)
 def report(self):return dict(enabled=True,epoch=self.hub.epoch,independent_producers=True,stock_holdback_s=0,counts=dict(self.count),published=dict(self.hub.count),admission=dict(self.admit.count),pending=len(self.admit.pending),stream_pending=len(self.jobs)+len(self.waiting),stats_pending=len(self.groups),coordinator_wall_s=self.wall_time,stream_child_cpu_s=self.stream_cpu_s)
 def close(self):self.executor.shutdown(wait=True,cancel_futures=True)

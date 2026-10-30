"""Finite read-only live observer of admitted DSP output. No production mutations."""
import asyncio,collections,ctypes,hashlib,json,math,os,re,runpy,select,stat,struct,sys,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'async-relay-20261030'))
from async_relay import AsyncFanIn,SOURCES
from rescue.feed import Records,unwrap,CORRECTION,MOD
D=Path('/dev/shm/adsb-async-live-20261030/data');P=Path('/run/adsb-rescue');old=runpy.run_path('/var/lib/adsb-fr24-stock-trial-20261030/trial.py')
WARM=35;MEASURE=180;TAIL=5

def readjson(p):return json.loads(Path(p).read_text())
def source_hashes():return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['src/rescue','models'] for p in (Path('/home/pi/adsb-neural-rescue')/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.so','.onnx')}
def health():
 s=old['snapshot']();baseline=readjson('/run/adsb-fr24-stock-trial-20261030/extended-status.json')['baseline'];old['health'](baseline,s,True)
 return dict(pids=s['pids'],fr24_pid=s['fr24_pid'],configs=s['configs'],gain_db=s['gain_db'],methods=s['methods'],capture_config=s['capture']['config'],samples={k:s['stock'][k] for k in ['samples_lost','samples_dropped']},fr24_host=s['fr24']['cfg_host'])
def live():
 s=readjson(P/'status.json');return dict(unix=time.time(),status_updated_unix=s['updated_unix'],metrics=s['method_metrics'],relay=readjson(P/'feed-status.json'))
class Output:
 def __init__(self,name):self.raw=(D/(name+'.beast')).open('wb');self.idx=(D/(name+'.chunks.jsonl')).open('w');self.bytes=0
 def write(self,raw,at=None):
  assert self.bytes+len(raw)<48*1024**2
  self.raw.write(raw);self.idx.write(json.dumps(dict(at=time.monotonic() if at is None else at,offset=self.bytes,bytes=len(raw)))+'\n');self.bytes+=len(raw)
 def close(self):self.raw.close();self.idx.close()
class Observer:
 def __init__(self):
  self.count=collections.Counter();self.stop=threading.Event();self.done=asyncio.Event();self.inbox=asyncio.Queue(1024);self.hubs={};self.core_cpu=collections.Counter();self.source_counts=collections.defaultdict(collections.Counter);self.stock_sha={};self.stock_delay={};self.source_rejections=collections.defaultdict(collections.Counter);self.positions=None
 def watch(self,loop):
  lib=ctypes.CDLL(None,use_errno=True);fd=lib.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC);assert fd>=0;assert lib.inotify_add_watch(fd,os.fsencode(P/'feed-outbox'),0x80|0x400)>=0
  def put(row):
   try:self.inbox.put_nowait(row)
   except asyncio.QueueFull:self.count['observer_queue_overflow']+=1
  self.watch_ready.set()
  try:
   while not self.stop.is_set():
    if not select.select([fd],[],[],.1)[0]:continue
    blob=os.read(fd,65536);at=0
    while at+16<=len(blob):
     wd,mask,cookie,length=struct.unpack_from('iIII',blob,at);name=blob[at+16:at+16+length].split(b'\0',1)[0].decode();at+=16+length
     if mask&0x4000:self.count['inotify_overflow']+=1
     if mask&0x400:self.count['outbox_deleted']+=1
     if not mask&0x80 or not re.fullmatch(r'\d+-\d+\.json',name):continue
     self.count['inotify_json_events']+=1
     try:
      f=os.open(P/'feed-outbox'/name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
      try:
       info=os.fstat(f);assert stat.S_ISREG(info.st_mode) and info.st_size<2*1024**2
       with os.fdopen(os.dup(f),'rb') as stream:data=stream.read()
      finally:os.close(f)
      row=dict(file=name,observed_mono=time.monotonic(),observed_unix=time.time(),sha256=hashlib.sha256(data).hexdigest(),batch=json.loads(data));self.count['batches_read']+=1;loop.call_soon_threadsafe(put,row)
     except FileNotFoundError:self.count['inotify_file_gone']+=1
     except Exception:self.count['outbox_read_errors']+=1
  finally:os.close(fd)
 def instrument(self,name,hub):
  out=Output(name);emissions=(D/(name+'.emissions.jsonl')).open('w');stock_sha=hashlib.sha256();self.stock_sha[name]=stock_sha;self.stock_delay[name]=[];self.stock_received_at=None
  stock=hub.relay.stock;batch=hub.relay.batch;ready=hub.relay.ready
  def measured_stock(*args,**kwargs):
   t=time.process_time();r=stock(*args,**kwargs);self.core_cpu[name]+=time.process_time()-t;return r
  def measured_batch(b,now,unix,enabled):
   source=b.get('extra',[{}])[0].get('source','none') if b.get('extra') else 'none';before=hub.relay.count.copy();t=time.process_time();result=batch(b,now,unix,enabled);self.core_cpu[name]+=time.process_time()-t
   for k,v in hub.relay.count.items():
    if v>before[k] and ('rejected' in k):self.source_rejections[name][source+':'+k]+=v-before[k]
   return result
  def measured_ready(now):
   pending=sorted(hub.relay.heap,key=lambda r:r[1]);t=time.process_time();raw=ready(now);self.core_cpu[name]+=time.process_time()-t;offset=0;sent=time.monotonic()
   for tick,seq,deadline,wire,source in pending:
    if raw[offset:offset+len(wire)]!=wire:
     self.count[name+'_not_emitted_'+source]+=1
     assert source!='stock','Original stock not emitted'
     continue
    offset+=len(wire)
    if source=='stock':
     stock_sha.update(wire)
     if self.stock_received_at is not None and self.measure_start<=sent<self.measure_end:self.stock_delay[name].append(sent-self.stock_received_at)
    else:
     emissions.write(json.dumps(dict(at=sent,unix=time.time(),source=source,ticks=tick,wire_hex=wire.hex()))+'\n');self.source_counts[name][source]+=1
   assert offset==len(raw),'Emission instrumentation failed to account for bytes'
   return raw
  hub.relay.stock=measured_stock;hub.relay.batch=measured_batch;hub.relay.ready=measured_ready
  publish=hub.publish
  def captured(raw):
   publish(raw)
   if raw:out.write(raw)
  hub.publish=captured
  return out,emissions
 async def stock(self):
  out=Output('stock');parser=Records();r,w=await asyncio.open_connection('127.0.0.1',30005)
  try:
   while not self.done.is_set():
    try:raw=await asyncio.wait_for(r.read(65536),1)
    except TimeoutError:continue
    if not raw:raise RuntimeError('Stock input closed')
    at=time.monotonic();out.write(raw,at);self.stock_received_at=at
    for wire,frame in parser.feed(raw):
     for hub in self.hubs.values():hub.stock(wire,frame,self.epoch)
   if parser.buffer:
    for hub in self.hubs.values():hub.stock(bytes(parser.buffer),None,self.epoch)
  finally:out.close();w.close();await w.wait_closed()
 async def actual(self):
  out=Output('actual');r,w=await asyncio.open_connection('127.0.0.1',31005)
  try:
   while not self.done.is_set():
    try:raw=await asyncio.wait_for(r.read(65536),1)
    except TimeoutError:continue
    if not raw:raise RuntimeError('Current relay input closed')
    out.write(raw)
  finally:out.close();w.close();await w.wait_closed()
 async def batches(self):
  with (D/'batches.jsonl').open('w') as out:
   while not self.done.is_set() or not self.inbox.empty():
    try:row=await asyncio.wait_for(self.inbox.get(),.1)
    except TimeoutError:continue
    out.write(json.dumps(row,separators=(',',':'))+'\n');batch=row['batch']
    groups=collections.defaultdict(list)
    for event in batch.get('extra',[]):groups[event['source']].append(event)
    for source,events in groups.items():
     self.count['observed_'+source]+=len(events)
     if source not in SOURCES:self.count['forbidden_source']+=len(events);continue
     for at in range(0,len(events),256):
      b=dict(batch,admission='production_guarded_v1',extra=events[at:at+256])
      for hub in self.hubs.values():hub.submit(source,b)
    self.inbox.task_done()
 async def context(self):
  origin=readjson('/run/readsb/receiver.json');(D/'receiver.private.json').write_text(json.dumps(origin));positions=(D/'positions.jsonl').open('w');last_health=0
  try:
   while not self.done.is_set():
    now=time.monotonic()
    if now-last_health>=5:assert health()==self.before,'Protected pipeline changed';last_health=now
    aircraft=readjson('/run/readsb/aircraft.json');positions.write(json.dumps(dict(observed_unix=time.time(),now=aircraft['now'],aircraft=[{k:a.get(k) for k in ['hex','lat','lon','seen_pos','nic','nac_p','mlat','tisb']} for a in aircraft['aircraft'] if 'lat' in a and 'lon' in a]),separators=(',',':'))+'\n')
    await asyncio.sleep(1)
  finally:positions.close()
 async def main(self):
  D.mkdir(exist_ok=False);self.before=health();hashes=source_hashes();self.epoch=self.before['pids']['readsb'];assert self.before['capture_config']['disk_limit_bytes']==5000000000
  self.start=time.monotonic();self.measure_start=self.start+WARM;self.measure_end=self.measure_start+MEASURE;self.end=self.measure_end+TAIL;self.cpu_start=time.process_time();self.watch_ready=threading.Event();loop=asyncio.get_running_loop();watch=threading.Thread(target=self.watch,args=(loop,),daemon=True);watch.start()
  while not self.watch_ready.is_set():await asyncio.sleep(.01)
  handles=[]
  for name,age in [('strict250',.25),('compat3000',3.)]:
   hub=AsyncFanIn(lambda:self.before['methods'],max_extra_age=age);self.hubs[name]=hub;handles.append(self.instrument(name,hub));hub.start()
  tasks=[asyncio.create_task(f()) for f in [self.stock,self.actual,self.batches,self.context]];boundaries={}
  try:
   while time.monotonic()<self.end:
    for task in tasks:
     if task.done():task.result();raise RuntimeError('Observer task ended early')
    now=time.monotonic()
    if now>=self.measure_start and 'start' not in boundaries:boundaries['start']=live()
    if now>=self.measure_end and 'end' not in boundaries:boundaries['end']=live()
    (D/'progress.json').write_text(json.dumps(dict(elapsed_s=now-self.start,count=dict(self.count),phase='warmup' if now<self.measure_start else 'measuring' if now<self.measure_end else 'tail')))
    await asyncio.sleep(.2)
  finally:
   self.stop.set();await asyncio.to_thread(watch.join,2);self.done.set();await asyncio.gather(*tasks)
   for hub in self.hubs.values():await asyncio.gather(*(q.join() for q in hub.queues.values()));await hub.close()
   for out,events in handles:out.close();events.close()
  after=health();assert self.before==after;assert hashes==source_hashes(),'Production library/model/source changed'
  actual_sha=hashlib.sha256((D/'stock.beast').read_bytes()).hexdigest();assert all(h.hexdigest()==actual_sha for h in self.stock_sha.values()),'Original stock byte-stream mismatch'
  result=dict(before=self.before,after=after,source_hashes=hashes,measurement_start=self.measure_start,measurement_end=self.measure_end,start=self.start,end=self.end,count=dict(self.count),boundaries=boundaries,relay_core_cpu_s=dict(self.core_cpu),observer_total_cpu_s=time.process_time()-self.cpu_start,wall_s=time.monotonic()-self.start,stock_sha256=actual_sha,stock_output_hashes={k:v.hexdigest() for k,v in self.stock_sha.items()},stock_enqueue_delay_s=self.stock_delay,rejections={k:dict(v) for k,v in self.source_rejections.items()},hub_reports={k:v.report() for k,v in self.hubs.items()},scope='Read-only producer outputs at actual arrival time. Existing whole-second grouping preserved. Test outputs private RAM only, not feeder input.')
  (D/'result.json').write_text(json.dumps(result,indent=2))
  (D/'manifest.json').write_text(json.dumps({str(p.relative_to(D)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in D.iterdir() if p.is_file() and p.name!='manifest.json'},indent=2))
if __name__=='__main__':asyncio.run(Observer().main())

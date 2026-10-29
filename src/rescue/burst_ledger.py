"""Capture-only TCP journals. Never writes to decoder/feeder input or config.

Full stock and actual relay streams are authoritative observations. Coordinator
method annotations arrive separately and remain explicitly best effort.
"""
import collections,json,select,socket,threading,time
from pathlib import Path
from .wire import BeastParser
PRE_SECONDS=30.;TAIL_SECONDS=8.;HISTORY_SECONDS=35.;HISTORY_LIMIT=8*1024**2
FILES=('stock-full.beast','unified.beast','ledger.jsonl')

class BurstLedger:
 def __init__(self,rec,network=True):
  self.rec=rec;self.history_limit=HISTORY_LIMIT;self.history=collections.deque();self.history_bytes=0;self.seq=0;self.last_saved=0;self.until=0.;self.last_drain=0.;self.lock=threading.RLock();self.stop=threading.Event();self.active=None;self.bursts=[];self.faults=0;self.count=collections.Counter();self.epoch=None;self.parsers={s:BeastParser() for s in ('stock','unified')}
  self.streams={s:dict(connected=False,since=0.,generation=0,connections=0,disconnects=0,bytes=0) for s in ('stock','unified')}
  self.thread=threading.Thread(target=self.run,daemon=True,name='capture-full-packet-ledger') if network else None
 def start(self):
  if self.thread:self.thread.start()
 def ingest(self,stream,data,epoch=None,now=None,**fields):
  now=time.monotonic() if now is None else now
  with self.lock:
   self.seq+=1
   if stream in self.streams and data:
    self.streams[stream]['last_data']=now
    try:
     frames=self.parsers[stream].feed(data)
     if frames:self.streams[stream]['latest_tick']=max(f['ticks_12mhz'] for f in frames)
    except ValueError:self.count['parser_errors']+=1;self.faults+=1;self.last_overflow=now;self.parsers[stream]=BeastParser()
   meta=dict(record='stream_chunk' if stream!='dsp_annotations' else 'dsp_annotation',sequence=self.seq,stream=stream,epoch=epoch,received_unix=time.time(),arrival_monotonic=now,**fields)
   blob=json.dumps(meta,separators=(',',':')).encode();size=len(data)+len(blob)
   if self.rec.pins:
    if not self.rec.pins.pin(data):self.count['history_lock_failures']+=1;self.faults+=1;self.last_overflow=now;return
    if not self.rec.pins.pin(blob):self.rec.pins.unpin(data);self.count['history_lock_failures']+=1;self.faults+=1;self.last_overflow=now;return
   self.history.append((self.seq,now,stream,data,blob));self.history_bytes+=size
   while self.history and (self.history[0][1]<now-HISTORY_SECONDS or self.history_bytes>self.history_limit):
    _,stamp,_,old,info=self.history.popleft();self.history_bytes-=len(old)+len(info)
    if stamp>=now-PRE_SECONDS:self.count['history_overflow']+=1;self.faults+=1;self.last_overflow=now
    if self.rec.pins:self.rec.pins.unpin(old);self.rec.pins.unpin(info)
 def connection(self,stream,connected,now=None):
  now=time.monotonic() if now is None else now
  with self.lock:
   state=self.streams[stream];state['connected']=connected
   if connected:state['since']=now;state['generation']+=1;state['connections']+=1;self.parsers[stream]=BeastParser();state['latest_tick']=None;state['last_data']=None
   else:state['disconnects']+=1;self.faults+=1
   self.ingest(stream,b'',self.epoch,now,event='connected' if connected else 'disconnected',generation=state['generation'])
 def run(self):
  sockets={};retry={s:0. for s in self.streams}
  try:
   while not self.stop.is_set():
    now=time.monotonic()
    for stream,port in (('stock',30005),('unified',31005)):
     if stream in sockets or now<retry[stream]:continue
     try:
      sock=socket.create_connection(('127.0.0.1',port),timeout=.2);sock.setblocking(False);sockets[stream]=sock;self.connection(stream,True)
     except OSError:
      retry[stream]=now+2
      with self.lock:self.count[stream+'_connect_failures']+=1
    ready,_,_=select.select(list(sockets.values()),[],[],.1) if sockets else ([],[],[])
    if not sockets:self.stop.wait(.1)
    for stream,sock in list(sockets.items()):
     if sock not in ready:continue
     try:
      blob=sock.recv(65536)
      if not blob:raise ConnectionError('Stream EOF')
      with self.lock:self.streams[stream]['bytes']+=len(blob);generation=self.streams[stream]['generation']
      self.ingest(stream,blob,self.epoch,generation=generation)
     except (OSError,ValueError,MemoryError):
      sock.close();del sockets[stream];retry[stream]=time.monotonic()+2;self.connection(stream,False)
  finally:
   for sock in sockets.values():sock.close()
 def ready(self,now=None):
  now=time.monotonic() if now is None else now
  with self.lock:return all(s['connected'] and now-s['since']>=PRE_SECONDS and s.get('last_data') is not None and now-s['last_data']<2 for s in self.streams.values()) and now-getattr(self,'last_overflow',-1e9)>=PRE_SECONDS and now-getattr(self,'epoch_changed',-1e9)>=PRE_SECONDS
 def set_epoch(self,epoch):
  if self.epoch!=epoch:
   if self.epoch is not None:self.faults+=1;self.count['clock_epoch_changes']+=1
   self.epoch=epoch;self.epoch_changed=time.monotonic()
 def append(self,row,closing=False,extra_reserve=0):
  blob=(json.dumps(row,separators=(',',':'))+'\n').encode()
  if closing and len(blob)>8192:self.count['oversize_end_marker']+=1;self.faults+=1;return False
  if not self.rec.allowance(len(blob)+extra_reserve,journal=True,closing=closing):self.count['journal_cap_skips']+=1;self.faults+=1;return False
  self.rec.batch.append('ledger.jsonl',blob);return True
 def snapshot(self):
  out={}
  for key,path in [('aircraft','/run/readsb/aircraft.json'),('stats','/run/readsb/stats.json'),('decoder','/run/adsb-rescue/status.json'),('relay','/run/adsb-rescue/feed-status.json')]:
   try:
    data=json.loads(Path(path).read_text())
    if key=='decoder':data={k:data.get(k) for k in ('started_unix','updated_unix','method_switches','alignment','input','workers','capture_transport')}
    out[key]=data
   except (OSError,ValueError):out[key]=None
  return out
 def begin_rf(self,epoch,sample,end,unix,rf_file='continuous.uc8',rf_offset=None):
  now=time.monotonic()
  if self.active and (self.active['epoch']!=epoch or self.active['sample_end']!=sample or self.active['rf_file']!=rf_file):self.end_rf()
  if self.active is None:
   # Refuse new RF before retaining any waveform bytes if its end marker
   # cannot be reserved. Existing bursts retain priority at a full RAM cap.
   if not self.rec.allowance(8192,journal=True):self.count['journal_admission_skips']+=1;self.count['journal_cap_skips']+=1;return None
   ident=f'{epoch}-{sample}-{self.rec.batch.lengths[rf_file] if rf_offset is None else rf_offset}'
   proposed=dict(burst_id=ident,epoch=epoch,sample_start=sample,sample_end=end,unix_start=unix,arrival_start=now,arrival_end=now,rf_file=rf_file,faults_start=self.faults,final_at=None)
   if not self.append(dict(record='rf_burst_begin',**proposed,pre_seconds=PRE_SECONDS,tail_seconds=TAIL_SECONDS,clock_correction_ticks=2398,ticks_per_sample=5,rf_byte_start=self.rec.batch.lengths[rf_file] if rf_offset is None else rf_offset,sample_rate=2400000,origin=getattr(self.rec,'origin',None),receiver_context=self.snapshot(),streams=self.status()['streams'],method_annotations_best_effort=True,training_eligible=False),extra_reserve=8192):return None
   self.active=proposed;self.bursts.append(self.active);self.count['bursts']+=1
   # Backfill the pre-window once. The journal is shared by overlapping bursts.
   self.drain(start=now-PRE_SECONDS,force=True)
  self.active.update(sample_end=end,arrival_end=now);self.until=max(self.until,now+TAIL_SECONDS)
  return self.active['burst_id']
 def end_rf(self):
  if self.active:
   self.active['final_at']=self.active['arrival_end']+TAIL_SECONDS;self.active=None
 def annotation(self,row,epoch):
  self.ingest('dsp_annotations',b'',epoch,annotation={k:v for k,v in row.items() if k!='wire_hex'},training_eligible=False,authoritative=False)
 def drain(self,start=None,force=False):
  now=time.monotonic()
  if not force and now-self.last_drain<.2:return
  self.last_drain=now
  if start is None and self.until<=0:return
  low=start if start is not None else -1e99;high=self.until if start is None else now
  with self.lock:
   entries=[]
   for item in reversed(self.history):
    if item[0]<=self.last_saved:break
    if low<=item[1]<=high:entries.append(item)
   for seq,stamp,stream,data,info in reversed(entries):
    row=json.loads(info);name={'stock':'stock-full.beast','unified':'unified.beast'}.get(stream)
    if name:row.update(file=name,byte_offset=self.rec.batch.lengths[name],bytes=len(data))
    metadata=(json.dumps(row,separators=(',',':'))+'\n').encode()
    if not self.rec.allowance(len(data)+len(metadata),journal=True):self.count['journal_cap_skips']+=1;self.faults+=1;continue
    if name:self.rec.batch.append(name,data)
    self.rec.batch.append('ledger.jsonl',metadata);self.last_saved=seq;self.count[stream+'_saved_bytes']+=len(data);self.count[stream+'_saved_chunks']+=1
  for burst in self.bursts:
   if burst.get('final_at') is not None and burst['final_at']<=now and not burst.get('finalized'):
    complete=self.faults==burst['faults_start'] and all(s['connected'] and s.get('latest_tick') is not None and s['latest_tick']>=burst['sample_end']*5+2398 and s.get('last_data') is not None and now-s['last_data']<2 for s in self.streams.values())
    if self.append(dict(burst,record='rf_burst_end',finalized=True,streams_complete=complete,coverage='TCP stock and actual relay streams; source annotations best effort',streams=self.status()['streams'],training_eligible=False),closing=True):
     burst['finalized']=True;burst['streams_complete']=complete;self.count['complete_bursts' if complete else 'incomplete_bursts']+=1
 def status(self):
  with self.lock:return dict(enabled=True,pre_seconds=PRE_SECONDS,tail_seconds=TAIL_SECONDS,history_bytes=self.history_bytes,history_limit_bytes=self.history_limit,ready=self.ready(),streams={k:dict(v) for k,v in self.streams.items()},counts=dict(self.count),faults=self.faults,recent_bursts=[{k:v for k,v in b.items() if k not in ('faults_start',)} for b in self.bursts[-4:]],source_annotation_completeness='best_effort_IPC; authoritative_actual_output_in_unified_beast')
 def close(self):
  self.stop.set()
  if self.thread:self.thread.join(timeout=2)
  with self.lock:
   if self.rec.pins:
    for _,_,_,data,info in self.history:self.rec.pins.unpin(data);self.rec.pins.unpin(info)
   self.history.clear();self.history_bytes=0

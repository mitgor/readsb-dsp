"""Bounded, loss-visible far-range Beast/packet-IQ and continuous-IQ capture.

Consumes copies from the existing readsb tap; never owns or backpressures SDR.
New dataset only: 5,000,000,000 byte hard disk cap, 12-hour bulk tar saves.
"""
import argparse,base64,collections,hashlib,io,json,math,os,select,socket,struct,tarfile,threading,time
from pathlib import Path
from .capture_triggers import CaptureTriggers,ExternalPoller
from .burst_ledger import BurstLedger,FILES as LEDGER_FILES
from .capture_schedule import CaptureSchedule
from .wire import BeastParser
from .telemetry import distance_nm,MemoryPins
HEADER=struct.Struct('<4sIIIQQQ');RATE=2400000;CORRECTION=2398
CONFIG=Path('/etc/default/adsb-far-capture.json')
DEFAULTS=dict(packet_capture=True,continuous_capture=True,threshold_nm=200.,ram_limit_bytes=256*1024**2,continuous_ram_bytes=192*1024**2,disk_limit_bytes=5000000000,flush_seconds=43200)
def config(path=CONFIG):
 c={**DEFAULTS,**(json.loads(path.read_text()) if path.exists() else {})}
 if set(c)!=set(DEFAULTS) or any(type(c[k]) is not bool for k in ('packet_capture','continuous_capture')):raise ValueError('Invalid capture switches')
 if c['threshold_nm']!=200 or c['disk_limit_bytes']!=5000000000 or c['flush_seconds']!=43200:raise ValueError('Capture threshold/cap/save policy is fixed')
 if not 16*1024**2<=c['ram_limit_bytes']<=256*1024**2 or not 0<=c['continuous_ram_bytes']<c['ram_limit_bytes']:raise ValueError('Invalid capture RAM limits')
 return c

def address(payload):
 """Same ICAO forms as pinned readsb; require a known stock position later."""
 try:b=bytes.fromhex(payload)
 except ValueError:return None
 if len(b) not in (7,14):return None
 df=b[0]>>3
 if df in (11,17):return b[1:4].hex()
 if df==18 and b[0]&7 in (0,2,6):return b[1:4].hex()
 if df not in (0,4,5,16,20,21,24,25,26,27,28,29,30,31):return None
 value=int.from_bytes(b,'big')
 for bit in range(len(b)*8-1,23,-1):
  if value&(1<<bit):value^=0x1fff409<<(bit-24)
 return f'{value:06x}'

def wire(frame):
 body=int(frame['ticks_12mhz']).to_bytes(6,'big')+bytes([frame.get('signal_byte',0)])+bytes.fromhex(frame['message_hex'])
 return bytes([26,frame.get('kind',51)])+body.replace(b'\x1a',b'\x1a\x1a')

class CaptureClient:
 def __init__(self,path='/run/adsb-far-capture/iq.sock'):
  self.path=str(path);self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);self.sock.setblocking(False);self.count=collections.Counter()
 def send(self,blob):
  try:self.sock.sendto(blob,self.path);self.count['sent']+=1
  except OSError:self.count['dropped']+=1
 def frames(self,epoch,rows):
  for lo in range(0,len(rows),32):self.send(b'RSE1'+json.dumps(dict(epoch=epoch,frames=rows[lo:lo+32]),separators=(',',':')).encode())
 def close(self):self.sock.close()

class Chain(io.RawIOBase):
 def __init__(self,parts):self.parts=iter(parts);self.part=b'';self.at=0;self.hash=hashlib.sha256()
 def read(self,n=-1):
  if n<0:raise ValueError('Bounded reads required')
  out=[];left=n
  while left:
   if self.at==len(self.part):
    try:self.part=next(self.parts);self.at=0
    except StopIteration:break
   take=min(left,len(self.part)-self.at);out.append(self.part[self.at:self.at+take]);self.at+=take;left-=take
  blob=b''.join(out);self.hash.update(blob);return blob

def tar_size(lengths):return ((sum(512+((n+511)//512)*512 for n in lengths)+1024+10239)//10240)*10240

class LockedPins(MemoryPins):
 def __init__(self):self._lock=threading.RLock();super().__init__()
 def pin(self,blob):
  with self._lock:return super().pin(blob)
 def unpin(self,blob):
  with self._lock:return super().unpin(blob)

class Batch:
 def __init__(self,pins=None):
  self.pins=pins;self.parts={k:[] for k in ('continuous.uc8','packets.uc8','stock.beast','packets.jsonl','segments.jsonl',*LEDGER_FILES)};self.lengths=collections.Counter();self.raw_index=[];self.events=0
 def append(self,name,blob):
  if self.pins and not self.pins.pin(blob):raise MemoryError('Capture RAM locking failed; collection paused')
  offset=self.lengths[name];self.parts[name].append(blob);self.lengths[name]+=len(blob);return offset
 def release(self):
  if self.pins:
   for parts in self.parts.values():
    for blob in parts:self.pins.unpin(blob)
 @property
 def bytes(self):return sum(self.lengths.values())
 def estimate(self,extra=0):return tar_size([*self.lengths.values(),65536+extra])

class Recorder:
 def __init__(self,directory,cfg=None,lock_memory=False):
  self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True);self.cfg=cfg or dict(DEFAULTS);self.pins=LockedPins() if lock_memory else None;self.batch=Batch(self.pins);self.inflight=0;self.lock=threading.Lock();self.writer=None;self.count=collections.Counter();self.last_error=None;self.next_flush=time.time()+self.cfg['flush_seconds'];self.epoch=None;self.ring=collections.deque();self.ring_bytes=0;self.expected=None;self.pending=collections.deque(maxlen=10000);self.seen={};self.positions={};self.health={};self.far_present=False;self.trigger_context={};self.ledger=None;self.failed_batch=None;self._disk_bytes=0;self._disk_checked=0
  self.schedule=CaptureSchedule(self.cfg['continuous_ram_bytes'],enabled=False)
 def disk_bytes(self,refresh=False):
  if refresh or time.monotonic()-self._disk_checked>2:
   self._disk_bytes=sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file());self._disk_checked=time.monotonic()
  return self._disk_bytes
 def allowance(self,n,continuous=False,journal=False,closing=False):
  with self.lock:
   # Ordinary RF/packet metadata cannot consume the bounded journal tail pool.
   # Journal data cannot consume the space promised to pending end markers.
   closures=8192*sum(not b.get('finalized') for b in self.ledger.bursts) if self.ledger else 0
   tail=min(16*1024**2,self.cfg['ram_limit_bytes']//8) if self.ledger and not journal else 0
   future_rf=max(0,self.cfg['continuous_ram_bytes']-self.batch.lengths['continuous.uc8']) if self.schedule.enabled and not continuous else 0
   reserve=0 if closing else closures+tail+future_rf
   if self.batch.bytes+self.inflight+n+reserve+(self.ledger.history_limit if self.ledger else 0)>self.cfg['ram_limit_bytes']:self.count['ram_cap_skips']+=1;return False
   if continuous and self.batch.lengths['continuous.uc8']+n>self.cfg['continuous_ram_bytes']:self.count['continuous_ram_cap_skips']+=1;return False
   # Include tar headers, terminal blocks, manifest reserve and in-flight bytes.
   if self.disk_bytes()+self.batch.estimate(n+reserve)+self.inflight>self.cfg['disk_limit_bytes']:self.count['disk_cap_skips']+=1;return False
  return True
 def iq(self,epoch,sample,unix,raw):
  if not raw or len(raw)%2:return
  self.clock_unix=unix;self.clock_sample=sample
  if self.ledger:self.ledger.set_epoch(epoch)
  if epoch!=self.epoch:
   if self.pending:self.count['epoch_change_pending_skips']+=len(self.pending)
   self.pending.clear()
   if self.pins:
    for _,blob in self.ring:self.pins.unpin(blob)
   self.ring.clear();self.ring_bytes=0;self.expected=None;self.epoch=epoch
  if self.expected is not None and sample!=self.expected:self.count['tap_gap_samples']+=abs(sample-self.expected)
  if self.pins and not self.pins.pin(raw):raise MemoryError('Capture rolling RAM locking failed')
  self.expected=sample+len(raw)//2;self.ring.append((sample,raw));self.ring_bytes+=len(raw)
  while self.ring and (self.ring[0][0]+len(self.ring[0][1])//2<sample-4*RATE or self.ring_bytes>24*1024**2):
   _,old=self.ring.popleft();self.ring_bytes-=len(old)
   if self.pins:self.pins.unpin(old)
  self.count['tap_samples_received']+=len(raw)//2
  retained=False
  if self.cfg['continuous_capture'] and self.far_present and (self.ledger is None or self.ledger.ready()) and self.schedule.permit(epoch,sample,unix,len(raw)//2):
   at=self.batch.lengths['continuous.uc8'];record=dict(record='continuous_segment',epoch=epoch,sample_start=sample,sample_count=len(raw)//2,unix=unix,sample_rate=RATE,file='continuous.uc8',byte_offset=at,bytes=len(raw),evaluation_only=True,training_eligible=False)
   # Write full trigger context only when it changes; every segment references it.
   context=json.dumps(self.trigger_context,sort_keys=True,separators=(',',':')).encode();context_id=hashlib.sha256(context).hexdigest();record['capture_context_id']=context_id
   if getattr(self.batch,'context_id',None)!=context_id:record['capture_context']=self.trigger_context
   metadata=(json.dumps(record,separators=(',',':'))+'\n').encode()
   journal_reserve=0
   if self.ledger:
    active=self.ledger.active;continuing=active and active['epoch']==epoch and active['sample_end']==sample and active['rf_file']=='continuous.uc8'
    record['burst_id']=active['burst_id'] if continuing else f'{epoch}-{sample}-{at}'
    if not continuing:journal_reserve=0 if self.schedule.enabled else 2*self.ledger.history_limit+2*1024**2
    metadata=(json.dumps(record,separators=(',',':'))+'\n').encode()
   if self.allowance(len(raw)+len(metadata)+journal_reserve,True):
    if self.ledger and self.ledger.begin_rf(epoch,sample,sample+len(raw)//2,unix,rf_offset=at) is None:
     self.count['journal_admission_skips']+=1;self.drain();return
    retained=True;self.batch.append('continuous.uc8',raw);self.batch.raw_index.append((epoch,sample,sample+len(raw)//2,at));self.batch.append('segments.jsonl',metadata);self.batch.context_id=context_id;self.count['continuous_samples']+=len(raw)//2
    self.schedule.recorded(epoch,sample,unix,len(raw)//2)
  if self.ledger and not retained:self.ledger.end_rf()
  self.drain()
 def position(self,addr,unix):
  values=self.positions.get(addr,())
  for value in reversed(values):
   stamp,distance=value[:2]
   if 0<=unix-stamp<=15:return distance,unix-stamp
  return None,None
 def frame(self,row,source='stock',epoch=None):
  if not self.cfg['packet_capture']:return
  p=row['message_hex'];addr=address(p);ticks=row.get('ticks',row.get('ticks_12mhz',0)-CORRECTION);unix=row.get('unix')
  # The sender supplies wall time for DSP; stock time is anchored by the same
  # readsb sample counter, never arrival time, once IQ has arrived.
  if unix is None:
   if not self.ring:self.count['packet_no_rf_clock']+=1;return
   unix=self.clock_unix+(ticks/5-self.clock_sample)/RATE
  d,age=self.position(addr,unix)
  if d is None:self.count['unrangeable_packets']+=1;return
  if d<=self.cfg['threshold_nm']:return
  key=(epoch or self.epoch,ticks,p)
  if key in self.seen:return
  self.seen[key]=time.monotonic()
  if len(self.seen)>20000:self.seen={k:t for k,t in self.seen.items() if time.monotonic()-t<10}
  if len(self.pending)==self.pending.maxlen:self.count['pending_cap_skips']+=1;return
  quality=next((v[2] for v in reversed(self.positions.get(addr,())) if len(v)>2 and 0<=unix-v[0]<=15),None)
  self.pending.append((time.monotonic(),dict(row,epoch=epoch or self.epoch,ticks=ticks,unix=unix,icao=addr,distance_nm=d,position_age_s=age,position_quality=quality,range_verified=False,source=source)))
  self.count['far_packets_seen']+=1;self.drain()
 def extract(self,lo,hi):
  parts=[];at=lo
  for start,raw in self.ring:
   end=start+len(raw)//2
   if end<=at:continue
   if start>at:return None
   take=min(end,hi);parts.append(raw[2*(at-start):2*(take-start)]);at=take
   if at>=hi:return b''.join(parts)
  return None
 def continuous_ref(self,epoch,lo,hi):
  at=lo;first=None;expected=None
  for e,start,end,offset in self.batch.raw_index:
   if e!=epoch or end<=at:continue
   if start>at:return None
   here=offset+2*(at-start)
   if first is None:first=here
   elif here!=expected:return None
   take=min(end,hi);expected=here+2*(take-at);at=take
   if at>=hi:return first
  return None
 def drain(self):
  while self.pending:
   created,row=self.pending[0];center=round(row['ticks']/5);lo=center-192;hi=center+576
   if self.expected is None or hi>self.expected:
    if time.monotonic()-created<3:break
   self.pending.popleft();raw=self.extract(lo,hi) if row['epoch']==self.epoch else None
   if raw is not None and self.ledger and not self.ledger.ready():raw=None;self.count['packet_ledger_unready']+=1
   if raw is None:self.count['packet_iq_missing']+=1
   ref=self.continuous_ref(row['epoch'],lo,hi) if raw is not None else None
   if self.schedule.enabled and ref is None and raw is not None:
    raw=None;self.count['packet_iq_outside_scheduled_rf']+=1
   packet_burst=None
   if raw is not None and self.ledger and ref is None:
    packet_burst=self.ledger.begin_rf(row['epoch'],lo,hi,row['unix']+(lo-center)/RATE,rf_file='packets.uc8',rf_offset=self.batch.lengths['packets.uc8']);self.ledger.end_rf()
    if packet_burst is None:raw=None;self.count['packet_ledger_admission_skips']+=1
   beast=bytes.fromhex(row['wire_hex']) if row.get('wire_hex') else wire(dict(row,ticks_12mhz=row['ticks']+CORRECTION))
   estimated=(len(raw) if raw else 0)+len(beast)+2048
   if not self.allowance(estimated):self.count['packet_cap_skips']+=1;continue
   boff=self.batch.lengths['stock.beast'];meta=dict(record='far_packet',**{k:v for k,v in row.items() if k!='wire_hex'},beast_file='stock.beast',beast_byte_offset=boff,beast_bytes=len(beast),beast_original=row['source']=='stock',raw_available=raw is not None,training_eligible=False,gain_db=self.health.get('gain_db'),position_provenance='prior_stock_only_15s')
   if raw is not None:
    name='continuous.uc8' if ref is not None else 'packets.uc8';at=ref if ref is not None else self.batch.append(name,raw)
    if packet_burst is not None:meta['burst_id']=packet_burst
    meta.update(iq_file=name,iq_byte_offset=at,iq_bytes=len(raw),iq_sha256=hashlib.sha256(raw).hexdigest(),sample_start=lo,event_sample_in_window=192,sample_rate=RATE,iq_format='unsigned_8bit_interleaved_IQ')
   packet_metadata=(json.dumps(meta,separators=(',',':'))+'\n').encode()
   if not self.schedule.permit_packet(row['unix'],len(beast)+len(packet_metadata)):self.count['scheduled_packet_skips']+=1;continue
   if self.schedule.enabled and not self.allowance(len(beast)+len(packet_metadata)):self.count['packet_cap_skips']+=1;continue
   self.batch.append('stock.beast',beast);self.batch.append('packets.jsonl',packet_metadata);self.batch.events+=1;self.count['far_packets_saved']+=1
   self.schedule.recorded_packet(len(beast)+len(packet_metadata))
 def flush(self,force=False):
  if self.ledger:
   self.ledger.drain(force=True)
   if time.monotonic()<self.ledger.until:return False
  if self.writer and self.writer.is_alive():return False
  if not force and time.time()<self.next_flush:return False
  retry=self.failed_batch is not None
  if not retry and not self.batch.bytes:self.next_flush=time.time()+self.cfg['flush_seconds'];return False
  if self.disk_bytes(refresh=True)+(self.failed_batch or self.batch).estimate()>self.cfg['disk_limit_bytes']:self.last_error='disk_cap';self.next_flush=time.time()+self.cfg['flush_seconds'];return False
  batch=self.failed_batch if retry else self.batch
  if not retry:batch.ledger_status=self.ledger.status() if self.ledger else None
  if not retry:
   self.batch=Batch(self.pins)
   if self.ledger:self.ledger.last_saved=0;self.ledger.bursts=[]
  self.failed_batch=None;self.inflight=batch.estimate();frozen_cfg=dict(self.cfg);frozen_schedule=self.schedule.report();self.next_flush=time.time()+self.cfg['flush_seconds']
  def write():
   target=self.directory/f'capture-{time.time_ns()}.tar';temporary=target.with_suffix('.partial')
   try:
    manifest=dict(schema='far-capture-v2',threshold_nm=frozen_cfg['threshold_nm'],sample_rate=RATE,config=frozen_cfg,capture_schedule=frozen_schedule,source='readsb_copy_tap_and_stock_beast_plus_guarded_dsp',files={},packets=batch.events,created_unix=time.time(),clock_correction_ticks=CORRECTION,counters=dict(self.count),packet_ledger=getattr(batch,'ledger_status',None))
    with tarfile.open(temporary,'w',format=tarfile.USTAR_FORMAT) as archive:
     for name,parts in batch.parts.items():
      reader=Chain(parts);entry=tarfile.TarInfo(name);entry.size=batch.lengths[name];archive.addfile(entry,reader);manifest['files'][name]=dict(bytes=entry.size,sha256=reader.hash.hexdigest())
     blob=json.dumps(manifest,indent=2).encode();entry=tarfile.TarInfo('manifest.json');entry.size=len(blob);archive.addfile(entry,io.BytesIO(blob))
    if self.disk_bytes(refresh=True)>self.cfg['disk_limit_bytes']:temporary.unlink();raise RuntimeError('Disk cap preflight mismatch')
    with temporary.open('rb') as f:os.fsync(f.fileno())
    os.replace(temporary,target);self.disk_bytes(refresh=True);self.count['saved_batches']+=1;self.last_error=None;batch.release()
   except Exception as e:
    # Preserve the detached RAM batch after failed save; never silently discard.
    temporary.unlink(missing_ok=True);self.disk_bytes(refresh=True);self.failed_batch=batch;self.last_error=repr(e)
   finally:
    with self.lock:self.inflight=0 if not self.last_error else batch.estimate()
  self.writer=threading.Thread(target=write,daemon=False);self.writer.start();return True
 def report(self):
  scope=('Hourly sampled far-range RF; packet/context metadata has a separate hourly byte quota. Packet IQ references scheduled RF only. All traffic in admitted RF bursts has full stock/actual-relay journals; incomplete coverage is flagged.' if self.schedule.enabled else 'All ranged stock Mode S/ADS-B and guarded DSP packets; unknown addresses/positions cannot be ranged. Continuous chunks and packet snippets share original UC8 when available.')
  return dict(capture_schedule=self.schedule.report(),packet_ledger=self.ledger.status() if self.ledger else None,capture_triggers=self.trigger_context,ram_lock_enabled=self.pins is not None,locked_page_bytes=len(self.pins.pages)*self.pins.page if self.pins else 0,enabled=self.cfg['packet_capture'] or self.cfg['continuous_capture'],config=self.cfg,counts=dict(self.count),ram_bytes=self.batch.bytes+self.inflight,ram_limit_bytes=self.cfg['ram_limit_bytes'],ring_bytes=self.ring_bytes,continuous_ram_bytes=self.batch.lengths['continuous.uc8'],disk_bytes=self.disk_bytes(),disk_limit_bytes=self.cfg['disk_limit_bytes'],next_flush_unix=self.next_flush,saving=bool(self.writer and self.writer.is_alive()),error=self.last_error,far_aircraft_present=self.far_present,pending_packets=len(self.pending),files=[dict(name=p.name,bytes=p.stat().st_size) for p in sorted(self.directory.glob('capture-*.tar'))],scope=scope+' Capture pauses at caps; counters expose gaps/skips.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=Path('/var/lib/adsb-far-capture'));p.add_argument('--runtime',type=Path,default=Path('/run/adsb-far-capture'));p.add_argument('--lat',type=float,required=True);p.add_argument('--lon',type=float,required=True);a=p.parse_args();a.runtime.mkdir(parents=True,exist_ok=True);rec=Recorder(a.directory,config(),lock_memory=True);path=a.runtime/'iq.sock';path.unlink(missing_ok=True);sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024**2);sock.bind(str(path));os.chmod(path,0o660);sock.setblocking(False);stock=None;parser=BeastParser(preserve_wire=True);stop=threading.Event()
 import signal
 for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
 rec.origin=(a.lat,a.lon);rec.schedule=CaptureSchedule(rec.cfg['continuous_ram_bytes']);rec.ledger=BurstLedger(rec);rec.ledger.start()
 last=0;retry=0;triggers=CaptureTriggers(rec.cfg['threshold_nm']);external=ExternalPoller((a.lat,a.lon),rec.cfg['threshold_nm']);external.start()
 # Runtime status survives clean collector restart; preserve the scheduled deadline.
 try:
  previous=json.loads((a.runtime/'status.json').read_text());deadline=previous['next_flush_unix'];rec.schedule.restore(previous.get('capture_schedule'))
  if time.time()<deadline<=time.time()+rec.cfg['flush_seconds']:rec.next_flush=deadline
 except (OSError,ValueError,KeyError,TypeError):pass
 try:
  while not stop.is_set():
   now=time.time()
   if stock is None and now>retry:
    try:stock=socket.create_connection(('127.0.0.1',30005),timeout=.2);stock.setblocking(False);parser=BeastParser(preserve_wire=True)
    except OSError:stock=None;retry=now+2
   ready,_,_=select.select([sock]+([stock] if stock else []),[],[],.05)
   if sock in ready:
    for _ in range(64):
     try:blob=sock.recv(65536)
     except BlockingIOError:break
     try:
      if blob[:4]==b'RSC1':
       magic,epoch,rate,n,sample,ns,dropped=HEADER.unpack_from(blob)
       if rate==RATE and n==len(blob)-HEADER.size and n%2==0:
        rec.count['readsb_tap_dropped_counter']=dropped;rec.iq(epoch,sample,ns/1e9,blob[HEADER.size:])
      elif blob[:4]==b'RSE1':
       data=json.loads(blob[4:])
       for row in data['frames']:
        rec.ledger.annotation(row,data['epoch']);rec.frame(row,row.get('source','dsp'),data['epoch'])
     except MemoryError:rec.count['ram_lock_failures']+=1
     except (ValueError,KeyError,TypeError,struct.error):rec.count['bad_datagrams']+=1
   if stock and stock in ready:
    try:
     blob=stock.recv(65536)
     if not blob:stock.close();stock=None;rec.count['stock_disconnects']+=1
     else:
      for row in parser.feed(blob):rec.frame(row)
    except MemoryError:rec.count['ram_lock_failures']+=1
    except (OSError,ValueError):stock.close();stock=None;rec.count['stock_disconnects']+=1
   rec.ledger.drain()
   if now-last>=1:
    try:
     rec.cfg=config();data=json.loads(Path('/run/readsb/aircraft.json').read_text());stats=json.loads(Path('/run/readsb/stats.json').read_text());rec.health=dict(gain_db=stats.get('gain_db'),local=stats.get('total',{}).get('local',{}));local_context=[]
     for row in data['aircraft']:
      if all(k in row for k in ('hex','lat','lon','seen_pos')) and not row['hex'].startswith('~'):
       stamp=data['now']-row['seen_pos'];distance=distance_nm(row['lat'],row['lon'],(a.lat,a.lon));h=rec.positions.setdefault(row['hex'],collections.deque(maxlen=40))
       quality=dict(nic=row.get('nic'),nac_p=row.get('nac_p'),lat=row['lat'],lon=row['lon'],passes_numeric_logger_criteria=all(isinstance(row.get(k),(int,float)) and row[k]>=5 for k in ('nic','nac_p')),mlat_fields=row.get('mlat',[]),tisb_fields=row.get('tisb',[]))
       if not h or stamp>h[-1][0]:h.append((stamp,distance,quality))
       if row['seen_pos']<=15:local_context.append(dict(icao=row['hex'],distance_nm=distance,last_seen_unix=data['now']-row.get('seen',100),position_unix=stamp,source='local_stock'))
     ext=external.snapshot();active=triggers.update(now,local_context,ext['tracks']);rec.far_present=bool(active);rec.trigger_context=dict(triggers.report(now),external={k:v for k,v in ext.items() if k!='tracks'},external_candidate_count=len(ext['tracks']))
     rec.positions={h:rows for h,rows in rec.positions.items() if rows and now-rows[-1][0]<60}
     if rec.far_present and now-getattr(rec,'context_saved',0)>=30 and (rec.cfg['packet_capture'] or rec.cfg['continuous_capture']):
      try:decoder=json.loads(Path('/run/adsb-rescue/status.json').read_text());decoder={k:decoder.get(k) for k in ('started_unix','updated_unix','method_switches','alignment','capture_transport','input','workers')}
      except (OSError,ValueError):decoder={}
      context=dict(record='receiver_context',unix=now,origin=dict(lat=a.lat,lon=a.lon),health=rec.health,decoder=decoder,aircraft=[r for r in data['aircraft'] if r.get('seen_pos',100)<=15 and r.get('hex') in rec.positions and rec.positions[r['hex']][-1][1]>rec.cfg['threshold_nm']],training_eligible=False)
      blob=(json.dumps(context,separators=(',',':'))+'\n').encode()
      if rec.schedule.permit_packet(now,len(blob)) and rec.allowance(len(blob)):
       rec.batch.append('segments.jsonl',blob);rec.context_saved=now;rec.schedule.recorded_packet(len(blob))
    except MemoryError:rec.count['ram_lock_failures']+=1
    except (OSError,ValueError,KeyError):
     rec.count['context_errors']+=1;rec.far_present=False;rec.trigger_context=dict(error='local_context_unavailable')
    rec.flush();s=rec.report();s['updated_unix']=time.time();tmp=a.runtime/'status.tmp';tmp.write_text(json.dumps(s));os.replace(tmp,a.runtime/'status.json');last=now
 finally:
  external.stop.set();rec.drain();rec.ledger.end_rf()
  while time.monotonic()<rec.ledger.until:
   rec.drain();rec.ledger.drain();time.sleep(.1)
  rec.ledger.drain(force=True);sock.close()
  if stock:stock.close()
  try:rec.drain()
  except MemoryError:rec.count['ram_lock_failures']+=1
  if rec.writer:rec.writer.join()
  rec.flush(force=True)
  if rec.writer:rec.writer.join()
  rec.ledger.close();path.unlink(missing_ok=True)
if __name__=='__main__':main()

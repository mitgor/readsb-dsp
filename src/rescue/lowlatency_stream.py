"""Opt-in production bridge. Consumes existing RF/worker completions, never an SDR.

All stock bytes still traverse the existing relay unchanged. Other DSP workers,
models, complete-window attribution and capture/training collection are retained.
Any runtime fault disables this branch; the caller resumes its executable path.
"""
import ctypes,hashlib,json,os,queue,threading,time
from collections import Counter,deque,OrderedDict
from pathlib import Path
from .latency_core.bindings import Decoder
from .latency_core.completion_bridge import Bridge
from .latency_core.cold_start import ColdStartRetry
from .latency_core.native_admission import NativeAdmission
from .latency_core.shared_energy import SharedEnergyFeed,EnergyAccounting,completion_from_block
from .latency_core.final_cache import RustCache
from .stock_history import StockHistory
from .streaming import CORE,TOTAL
from .stream1090_compare import compare

CONFIG=Path('/etc/default/adsb-stream1090-lowlatency.json')
class Accounting(EnergyAccounting):
 def __init__(self):super().__init__();self.order=deque();self.jobs=0;self.cpu=0.
 def record(self,key,value):
  if key in self._producer:
   if self._producer[key]!=value:raise ValueError('Conflicting energy completion receipt')
   return
  self._producer[key]=value;self.order.append(key);self.jobs+=1;self.cpu+=value
  while len(self.order)>4096:self._producer.pop(self.order.popleft(),None)
 def summary(self,*_):return dict(unique_upstream_jobs=self.jobs,reported_energy_CPU_s=self.cpu,adapter_cpu_s=self.adapter_cpu_s,duplicate_energy_decodes=0)

class TimedDecoder(Decoder):
 def invoke(self,operation,ctx,raw=None,first=None):
  n=ctypes.c_uint32();wall=time.monotonic();cpu=time.thread_time()
  if raw is None:rc=self.inc.stream1090_incremental_finish(ctx,self.buf,len(self.buf),ctypes.byref(n),100000)
  else:rc=self.inc.stream1090_incremental_feed(ctx,raw,len(raw)//2,first,self.buf,len(self.buf),ctypes.byref(n),100000)
  if rc:raise RuntimeError('Incremental '+operation+' failed: '+str(rc)+' '+json.dumps(dict(wall_s=time.monotonic()-wall,thread_cpu_s=time.thread_time()-cpu,samples=None if raw is None else len(raw)//2)))
  return self.rows(n.value)
 def feed(self,ctx,raw,first):
  return self.invoke('decoder',ctx,raw,first)
 def finish(self,ctx):
  return self.invoke('finish',ctx)

class LowLatency:
 def __init__(self,live,cfg,runtime,config_path=CONFIG):
  self.live=live;self.cfg=cfg;self.path=Path(config_path);self.runtime=Path(runtime);self.failed=False;self.error=None;self.stop=threading.Event();self.count=Counter();self.iq=queue.Queue(128);self.stock=queue.Queue(100000);self.completed=queue.Queue(4096);self.history=StockHistory();self.epoch=None;self.expired_before=-1;self.windows=OrderedDict();self.energy_pending={};self.pre_epoch_energy=deque();self.latest_iq_epoch=None;self.pending_emit=[];self.pending_audits=[];self.native_cpu_total=0.;self.cpu_by_window={};self.last_cfg=0.;self.serial=0
  for name in ['batch','incremental','admission','dedup']:
   entry=cfg[name];assert hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()==entry['sha256'],name+' checksum'
  self.decoder=TimedDecoder(cfg['batch']['path'],cfg['incremental']['path']);self.admission=NativeAdmission(cfg['admission']['path']);self.cache=RustCache(cfg['dedup']['path'],0);self.accounting=Accounting()
  self.thread=threading.Thread(target=self.decode,name='incremental-stream1090',daemon=True);self.thread.start()
 def fail(self,exc):
  if self.failed:return
  self.failed=True;self.error=repr(exc);self.count['failures']+=1;self.stop.set()
  try:(self.runtime/'lowlatency-error.json').write_text(json.dumps(dict(unix=time.time(),error=self.error,fallback='original executable')))
  except OSError:pass
 def offer_iq(self,epoch,sample,raw):
  if self.failed:return
  self.latest_iq_epoch=epoch
  try:self.iq.put_nowait((epoch,sample,raw))
  except queue.Full:self.fail(RuntimeError('Bounded incremental IQ queue full'))
 def offer_stock(self,frame):
  if self.failed:return
  try:self.stock.put_nowait(frame)
  except queue.Full:self.fail(RuntimeError('Bounded stock queue full'))
 def publish(self,item):
  try:self.completed.put_nowait(item)
  except queue.Full:self.fail(RuntimeError('Bounded completion queue full'))
 def decode(self):
  ctx=None;expected=None;epoch=None;buf=bytearray();cursor=0;first=0;cpu=0.
  try:
   if self.cfg.get('cpus') and hasattr(os,'sched_setaffinity'):
    os.sched_setaffinity(0,set(self.cfg['cpus']) & os.sched_getaffinity(0))
   while not self.stop.is_set():
    try:e,s,raw=self.iq.get(timeout=.1)
    except queue.Empty:continue
    if e!=epoch or s!=expected:
     if ctx:self.decoder.close(ctx);ctx=None
     skip=(-s)%3;first=s+skip;buf=bytearray(raw[skip*2:]);cursor=0;epoch=e;cpu=0.;self.publish(('epoch',e,first))
    else:buf.extend(raw)
    expected=s+len(raw)//2
    while not self.stop.is_set():
     if ctx is None:
      ctx=self.decoder.begin(first,TOTAL);cursor=0;cpu=0.;self.publish(('begin',epoch,first))
     stop=min(TOTAL,cursor+48000)
     if len(buf)//2<stop:break
     before=time.thread_time();rows=self.decoder.feed(ctx,bytes(buf[cursor*2:stop*2]),first+cursor);last=stop==TOTAL
     if last:rows+=self.decoder.finish(ctx)
     used=time.thread_time()-before;cpu+=used;cursor=stop;wm=first*5+(stop//8208*8208)*5-6000
     if last:wm=(first+600+CORE)*5+1440
     self.publish(('native',epoch,first,rows,wm,last,used))
     if last:
      self.decoder.close(ctx);ctx=None;del buf[:CORE*2];first+=CORE
     if len(buf)>TOTAL*2+120000:raise RuntimeError('Incremental raw bound exceeded')
  except BaseException as exc:self.fail(exc)
  finally:
   if ctx:self.decoder.close(ctx)
 def reset(self,epoch):
  same=self.epoch==epoch
  self.epoch=epoch
  # An IQ gap resets RF windows, not the receiver's already-arrived stock truth.
  # Rebuilding these same indexes on every gap can pin the coordinator for tens
  # of seconds. Keep their bounded contents and exact causal admission state.
  if not same:
   self.history=StockHistory();self.admission.reset(epoch)
   self.cache.lib.ec_reset(self.cache.h,epoch);self.cache.epoch=epoch
  else:self.count['same_epoch_stock_rebuilds_avoided']+=1
  self.bridge=Bridge(epoch,self.emit,admission=self.admission,retry=ColdStartRetry());self.shared=SharedEnergyFeed(epoch,self.bridge.offer,accounting=self.accounting);self.windows.clear();self.energy_pending.clear();self.expired_before=-1;self.count['epochs']+=1
 def begin(self,first):
  if first<=self.expired_before:return False
  if first in self.windows:return True
  # Only the optional early lane expires. The legacy full-window assembler
  # and executable fallback still own every completed grouped comparison.
  while self.windows:
   key=next(iter(self.windows))
   if key+4*CORE>first and len(self.windows)<16:break
   old=self.bridge.windows.pop(key);self.bridge.retry.close(key)
   self.shared.windows.pop(key,None);self.windows.pop(key);self.cpu_by_window.pop(key,None);self.energy_pending.pop(key,None)
   self.expired_before=max(self.expired_before,key)
   if not old['finalized']:self.count['retired_incomplete_early_windows']+=1
  case=dict(first=first,epoch=self.epoch);self.bridge.begin(first,case);self.shared.begin_case(first,case);self.windows[first]=case;return True
 def offer_completion(self,batch,rows,detail):
  if self.failed or detail.get('worker_role')!='dsp':return
  if batch.epoch!=self.epoch:
   if self.epoch is None or batch.epoch==self.latest_iq_epoch:
    if len(self.pre_epoch_energy)>=128:self.fail(RuntimeError('Pre-epoch energy receipt cap'));return
    self.pre_epoch_energy.append((batch,rows,detail))
   return
  try:
   if not self.begin(batch.first):return
   lo,hi=detail['block_range'];pending=self.energy_pending.setdefault(batch.first,{})
   for index in range(lo,hi):
    if index in pending:raise RuntimeError('Repeated energy block')
    a=batch.first*5+index*600000;b=a+600000
    owned=[dict(r,ticks=batch.first*5+r['sample_4msps']*3) for r in rows if r['source']=='energy' and a<=batch.first*5+r['sample_4msps']*3<b]
    pending[index]=(owned,float(detail.get('cpu_method_energy_s',0))/(hi-lo))
   w=self.shared.windows.get(batch.first)
   if w is None:return
   while w.sequence in pending:
    index=w.sequence;items,used=pending.pop(index);c=completion_from_block(epoch=batch.epoch,window=batch.first,index=index,first=batch.first,total_samples=TOTAL,stop=min(TOTAL,(index+1)*120000),rows=items,available_s=time.monotonic(),producer_cpu_s=used)
    self.shared.submit(c,time.monotonic());self.count['shared_energy_blocks']+=1;self.energy_changed=True
    if c.done:break
  except BaseException as exc:self.fail(exc)
 def emit(self,row,audit,now,lane):
  t=int(row['ticks']);p=row['message_hex'];latest=self.admission.latest_stock_tick
  if latest is None or not 0<=latest-t<=36000000:self.count['age_rejected']+=1;return
  if self.cache.push(1 if row['source']=='stream1090' else 2,t,p,now):
   assert audit['verified'] and audit['matches']>=20 and audit['median_abs_error_us']<=2
   self.pending_emit.append(dict(row));self.pending_audits.append(dict(audit));self.count['emitted_'+row['source']]+=1;self.count['lane_'+lane]+=1
 def tick(self):
  if self.failed:return
  try:
   now=time.monotonic()
   if now-self.last_cfg>1:
    self.last_cfg=now
    if not json.loads(self.path.read_text()).get('enabled'):raise RuntimeError('Low-latency selection disabled')
   changed=False
   for _ in range(4096):
    try:event=self.completed.get_nowait()
    except queue.Empty:break
    kind,e,first,*parts=event
    if kind=='epoch':
     self.reset(e)
     continue
    if e!=self.epoch:continue
    if not self.begin(first):continue
    if kind=='native':
     rows,wm,last,used=parts;self.bridge.offer(first,'native',e,rows,wm,last);self.cpu_by_window[first]=self.cpu_by_window.get(first,0)+used;self.native_cpu_total+=used;self.count['native_chunks']+=1
     if last:self.count['native_seconds']+=1
    changed=True
   if self.epoch is None:return
   if self.pre_epoch_energy:
    early=self.pre_epoch_energy;self.pre_epoch_energy=deque()
    for batch,rows,detail in early:
     if batch.epoch==self.epoch:self.offer_completion(batch,rows,detail)
   for _ in range(10000):
    try:row=self.stock.get_nowait()
    except queue.Empty:break
    self.history.append(row);self.bridge.on_stock(row);self.cache.push(0,int(row['ticks']),row['message_hex'],now);changed=True
   if self.live is not None:
    with self.live.lock:context_stamp=self.live.health.get('aircraft_unix',0)
    if time.time()-context_stamp>5:return
   if changed or getattr(self,'energy_changed',False):
    self.bridge.drain(self.history,self.admission.latest_stock_tick,now);self.energy_changed=False
   self.flush()
  except BaseException as exc:self.fail(exc)
 def flush(self):
  if not self.pending_emit:return
  out=self.runtime/'feed-outbox';out.mkdir(exist_ok=True)
  if len(list(out.glob('*.json')))>500:raise RuntimeError('Feed outbox cap')
  self.serial+=1;tmp=out/f'low-{os.getpid()}.tmp';tmp.write_text(json.dumps(dict(created_unix=time.time(),epoch=self.epoch,alignment=dict(verified=all(a['verified'] for a in self.pending_audits),matches=min(a['matches'] for a in self.pending_audits),median_abs_error_us=max(a['median_abs_error_us'] for a in self.pending_audits)),extra=self.pending_emit)))
  tmp.replace(out/f'low-{time.monotonic_ns()}-{self.serial}.json');self.count['outbox_frames']+=len(self.pending_emit);self.pending_emit=[];self.pending_audits=[]
 def stream_rows(self,first,epoch):
  if self.failed or epoch!=self.epoch:return None,0.
  w=self.bridge.windows.get(first) if self.epoch is not None else None
  if not w or not w['native_done']:return None,0.
  stock=[(t,p) for p in {m for t,m in w['native']} for t in self.history.payloads.get(p,()) if w['start']-60000<=t<w['end']+60000]
  audit,extras=compare(w['native'],stock)
  if not audit['aligned']:return [],self.cpu_by_window.get(first,0.)
  return [dict(source='stream1090',ticks=t,message_hex=m) for t,m in extras if w['start']<=t<w['end']],self.cpu_by_window.get(first,0.)
 def report(self):return dict(enabled=not self.failed,backend='incremental_native' if not self.failed else 'executable_fallback',requested_backend='incremental_native',last_error=self.error,counts=dict(self.count),bridge=dict(self.bridge.count) if self.epoch is not None else {},shared=self.accounting.summary(),dedup=self.cache.counts(),iq_pending=self.iq.qsize(),native_CPU_s=self.native_cpu_total)
 def close(self):
  self.stop.set();self.thread.join(timeout=3)
  if self.thread.is_alive():raise RuntimeError('Incremental thread did not stop')
  self.admission.close();self.cache.close()

def configured(live,methods,runtime,config_path=CONFIG):
 path=Path(config_path)
 if not path.exists():return None
 cfg=json.loads(path.read_text())
 if not cfg.get('enabled') or not methods.get('energy') or not methods.get('stream1090'):return None
 try:return LowLatency(live,cfg,runtime,path)
 except Exception as exc:
  try:(Path(runtime)/'lowlatency-error.json').write_text(json.dumps(dict(unix=time.time(),error=repr(exc),fallback='original executable')))
  except OSError:pass
  return None

class CompletionTap:
 """Observe existing futures before ordered grouping consumes them. No new work."""
 def __init__(self,pool):self.pool=pool;self.seen=set();self.ready=[]
 def collect(self,records):
  for batch,tasks,submitted,path in records:
   for task in tasks:
    if task in self.seen or not task.done():continue
    rows,detail=task.result();self.seen.add(task)
    if detail.get('worker_role')=='dsp':
     if len(self.ready)>=4096:raise RuntimeError('Completion tap cap')
     self.ready.append((batch,rows,detail))
 def pop(self):
  before=list(self.pool.pending);self.collect(before);result=self.pool.pop();self.collect(before);self.collect(list(self.pool.pending));self.seen.intersection_update({task for b,tasks,s,p in self.pool.pending for task in tasks});return result
 def take(self):
  out=self.ready;self.ready=[];return out

"""Experimental async fan-in; never routes a feeder or opens SDR/mirror inputs.

All producers must provide already admitted packets. Relay rechecks CRC, clock,
prior-stock identity, duplicate/conflict, enabled-source and freshness policy.
No global DSP completion barrier, timestamp-sort heap, or stock holdback.
"""
import argparse,asyncio,json,math,os,sys,time
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'latency-publication-20261030'))
from prototype import ImmediateRelay
from dedup import HistoryMerge
from rescue.feed import Records
SOURCES=frozenset(('energy','timing','soft','matched','coherent','sequence','acquisition','header','sic','neural','pulse','stream1090'))
FORBIDDEN_PORTS=frozenset((30001,30002,30003,30004,30005,31005,8754,8911))

class Subscriber:
 def __init__(self,writer,hub,capacity=256,timeout=.1):
  self.writer=writer;self.hub=hub;self.queue=asyncio.Queue(capacity);self.timeout=timeout;self.closed=False;self.task=asyncio.create_task(self.run())
 def close(self):
  if self.closed:return
  self.closed=True;self.hub.clients.discard(self);self.writer.close()
  while not self.queue.empty():self.queue.get_nowait();self.queue.task_done()
  if self.task is not asyncio.current_task():self.task.cancel()
 async def run(self):
  try:
   while not self.closed:
    raw=await self.queue.get()
    try:self.writer.write(raw);await asyncio.wait_for(self.writer.drain(),self.timeout);self.hub.count['client_bytes']+=len(raw)
    finally:self.queue.task_done()
  except (ConnectionError,TimeoutError,asyncio.CancelledError):pass
  finally:self.close()

class AsyncFanIn:
 def __init__(self,switches,queue_capacity=64,max_extra_age=.250):
  self.relay=ImmediateRelay(HistoryMerge,allowed_sources=SOURCES,max_extra_age=max_extra_age);self.switches=switches;self.clients=set();self.queues={s:asyncio.Queue(queue_capacity) for s in SOURCES};self.count=Counter();self.tasks=[]
 def start(self):self.tasks=[asyncio.create_task(self.worker(s)) for s in sorted(SOURCES)]
 def publish(self,raw):
  if not raw:return
  self.count['output_bytes']+=len(raw)
  for client in list(self.clients):
   try:client.queue.put_nowait(raw)
   except asyncio.QueueFull:self.count['slow_client_closed']+=1;client.close()
 def stock(self,wire,frame,epoch,now=None):
  # No awaits: update history and enqueue output atomically on the event loop.
  now=time.monotonic() if now is None else now
  self.relay.stock(wire,frame,now,epoch=epoch);self.publish(self.relay.ready(now));self.count['stock_input_bytes']+=len(wire)
 def submit(self,source,batch):
  if source not in SOURCES:self.count['unknown_source']+=1;return False
  try:self.queues[source].put_nowait((batch,time.monotonic()));return True
  except asyncio.QueueFull:self.count['queue_full_'+source]+=1;return False
 async def worker(self,source):
  while True:
   batch,queued=await self.queues[source].get()
   try:
    audit=batch.get('alignment',{});events=batch.get('extra',[])
    median=audit.get('median_abs_error_us');matches=audit.get('matches')
    good=(batch.get('admission')=='production_guarded_v1' and audit.get('verified') is True and type(matches) is int and matches>=20 and type(median) in (int,float) and math.isfinite(median) and 0<=median<=2)
    if not good or not isinstance(events,list) or len(events)>256 or any(not isinstance(e,dict) or e.get('source')!=source for e in events):self.count['invalid_contract_'+source]+=1;continue
    # Small slices yield to stock/other producers even when one source bursts.
    for start in range(0,len(events),8):
     enabled=self.switches();before=self.relay.count['dsp_frames_relayed'];now=time.monotonic()
     self.relay.batch({**batch,'extra':events[start:start+8]},now,time.time(),enabled);self.publish(self.relay.ready(now));self.count['emitted_'+source]+=self.relay.count['dsp_frames_relayed']-before
     await asyncio.sleep(0)
    self.count['batches_'+source]+=1
   except (ValueError,TypeError,KeyError,OverflowError,AttributeError):self.count['malformed_'+source]+=1
   finally:self.queues[source].task_done()
 async def close(self):
  for t in self.tasks:t.cancel()
  await asyncio.gather(*self.tasks,return_exceptions=True)
  subscribers=list(self.clients)
  for c in subscribers:c.close()
  await asyncio.gather(*(c.task for c in subscribers),return_exceptions=True)
 def report(self):
  self.relay.cache.prune(time.monotonic())
  return dict(counts=dict(self.count),relay_counts=dict(self.relay.count),dedup=dict(self.relay.cache.count),history_entries=len(self.relay.cache.expiry),history_seconds=self.relay.cache.ttl,queues={s:q.qsize() for s,q in self.queues.items()},stock_holdback_seconds=0,research_only=True,forwarded_to_fr24=False)

async def serve(args):
 if args.port in FORBIDDEN_PORTS:raise ValueError('Production port forbidden')
 if args.runtime.exists():raise ValueError('Use a new owned runtime directory')
 args.runtime.mkdir(mode=0o700,parents=True);switch_path=args.switches
 def switches():
  d=json.loads(switch_path.read_text());assert isinstance(d,dict) and set(d)<=SOURCES and all(type(v) is bool for v in d.values());return d
 switches();hub=AsyncFanIn(switches);hub.start();epoch=0;stop=asyncio.Event()
 async def client(reader,writer):
  c=Subscriber(writer,hub);hub.clients.add(c)
  try:
   while await reader.read(4096):pass
  finally:c.close()
 async def producer(reader,writer):
  try:
   while line:=await reader.readline():
    if len(line)>65536:break
    try:d=json.loads(line);hub.submit(d['producer'],d['batch'])
    except (ValueError,KeyError,TypeError):hub.count['malformed_ipc']+=1
  finally:writer.close()
 async def stock():
  nonlocal epoch
  while True:
   parser=Records();writer=None;epoch+=1
   try:
    reader,writer=await asyncio.open_connection('127.0.0.1',args.stock_port)
    while True:
     raw=await reader.read(65536)
     if not raw:break
     for wire,frame in parser.feed(raw):hub.stock(wire,frame,epoch)
   except OSError:hub.count['stock_disconnect']+=1
   finally:
    if parser.buffer:hub.stock(bytes(parser.buffer),None,epoch)
    if writer:writer.close()
    # New upstream epoch closes test consumers rather than mixing clock domains.
    for c in list(hub.clients):c.close()
   await asyncio.sleep(1)
 async def status():
  while True:
   tmp=args.runtime/'status.tmp';tmp.write_text(json.dumps(hub.report(),indent=2));tmp.replace(args.runtime/'status.json');await asyncio.sleep(1)
 tcp=await asyncio.start_server(client,'127.0.0.1',args.port);ipc=await asyncio.start_unix_server(producer,str(args.runtime/'ipc.sock'),limit=65537);os.chmod(args.runtime/'ipc.sock',0o600)
 (args.runtime/'endpoint.json').write_text(json.dumps(dict(host='127.0.0.1',port=tcp.sockets[0].getsockname()[1],ipc=str(args.runtime/'ipc.sock'))))
 tasks=[asyncio.create_task(stock()),asyncio.create_task(status())]
 try:
  async with tcp,ipc:await asyncio.sleep(args.seconds)
 finally:
  for t in tasks:t.cancel()
  await asyncio.gather(*tasks,return_exceptions=True);await hub.close();(args.runtime/'final.json').write_text(json.dumps(hub.report(),indent=2));(args.runtime/'ipc.sock').unlink(missing_ok=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--switches',type=Path,required=True);p.add_argument('--port',type=int,default=0);p.add_argument('--stock-port',type=int,default=30005);p.add_argument('--seconds',type=float,default=60);a=p.parse_args()
 if not 0<a.seconds<=600:p.error('Finite test runtime must be <=600s')
 asyncio.run(serve(a))

"""Production asynchronous relay; stock preserved, final shared transmission cache."""
import argparse,asyncio,json,time,os
from pathlib import Path
from . import feed as base
from .pipeline import settings
from .async_immediate import ImmediateRelay
from .async_dedup import HistoryMerge
SOURCES=base.ALLOWED
class Relay(ImmediateRelay):
 def __init__(self,config=None,worker_config=None):
  super().__init__(HistoryMerge,allowed_sources=SOURCES,max_extra_age=3,config=config);self.cache.reset(None);self.worker_config=Path(worker_config) if worker_config else None
 def batch(self,batch,now,unix):
  audit=batch.get('alignment',{});source=batch.get('producer');events=batch.get('extra',[])
  if not(batch.get('admission')=='production_guarded_v1' and source in SOURCES and len(events)<=256 and all(r.get('source')==source for r in events) and audit.get('verified') is True and type(audit.get('matches')) is int and audit['matches']>=20 and isinstance(audit.get('median_abs_error_us'),(int,float)) and 0<=audit['median_abs_error_us']<=2):self.count['contract_rejected']+=1;return
  epoch=batch.get('epoch')
  if type(epoch) is not int:self.count['invalid_epoch']+=1;return
  if self.epoch is None:
   self.epoch=epoch;self.cache.reset(epoch)
   for tick,payload in self.history:
    if self.anchor-tick<=60000000:self.cache.push('stock',epoch,tick,payload,now,validated=True)
  enabled=settings(self.config);worker=self.worker_config
  w=json.loads(worker.read_text()) if worker and worker.exists() else {}
  enabled.update(sequence=bool(w.get('sequence_acquisition') and w.get('sequence_enabled')),acquisition=bool(w.get('sequence_acquisition') and w.get('acquisition_enabled')))
  super().batch(batch,now,unix,enabled)
 def reset_source(self):
  super().reset_source();self.epoch=None
  if hasattr(self,'cache'):self.cache.reset(None)
 def ready(self,now):
  return super().ready(now)
 def report(self):
  result=super().report();self.cache.prune(time.monotonic());result.update(asynchronous=True,dedup_history_s=5,max_extra_age_s=3,dedup=dict(self.cache.count),cache_entries=len(self.cache.expiry),epoch=self.epoch);return result
class Subscriber:
 def __init__(self,writer,relay):self.writer=writer;self.relay=relay;self.queue=asyncio.Queue(256);self.task=asyncio.create_task(self.run());self.closed=False
 def close(self):
  if self.closed:return
  self.closed=True;self.relay.clients.discard(self);self.writer.close()
  if self.task is not asyncio.current_task():self.task.cancel()
 async def run(self):
  try:
   while True:
    raw=await self.queue.get()
    try:self.writer.write(raw);await asyncio.wait_for(self.writer.drain(),.5);self.relay.count['client_bytes_sent']+=len(raw)
    finally:self.queue.task_done()
  except (ConnectionError,TimeoutError,asyncio.CancelledError):pass
  finally:self.close()
async def run(a):
 relay=Relay(a.config,getattr(a,"worker_config",None));outbox=a.runtime/'feed-outbox';outbox.mkdir(exist_ok=True)
 def publish(raw):
  if not raw:return
  for c in list(relay.clients):
   try:c.queue.put_nowait(raw)
   except asyncio.QueueFull:relay.count['slow_clients_closed']+=1;c.close()
 async def client(reader,writer):
  c=Subscriber(writer,relay);relay.clients.add(c)
  try:
   while await reader.read(4096):pass
  finally:c.close()
 async def upstream():
  while True:
   writer=None;parser=base.Records()
   try:
    reader,writer=await asyncio.wait_for(asyncio.open_connection('127.0.0.1',a.stock_port),10);relay.connection_stock_base=relay.count['stock_bytes_relayed'];relay.connected=True;relay.connected_since=time.time();relay.upstream_error=None;relay.count['upstream_connections']+=1
    while True:
     try:raw=await asyncio.wait_for(reader.read(65536),15)
     except asyncio.TimeoutError:relay.count['stock_idle_timeouts']+=1;continue
     if not raw:raise ConnectionError('Stock disconnected')
     # Enqueue one existing TCP read, so a burst cannot fill client queues
     # before their writers get an event-loop turn. No timer or holdback.
     pieces=[]
     for wire,frame in parser.feed(raw):relay.stock(wire,frame,time.monotonic());pieces.append(relay.ready(time.monotonic()))
     publish(b''.join(pieces));await asyncio.sleep(0)
   except (OSError,asyncio.TimeoutError) as e:relay.count['upstream_disconnects']+=1;relay.upstream_error=type(e).__name__+': '+str(e)
   finally:
    relay.connected=False;relay.connected_since=None
    if parser.buffer:relay.stock(bytes(parser.buffer),None,time.monotonic());publish(relay.ready(time.monotonic()))
    if writer:writer.close()
    for c in list(relay.clients):c.close()
    relay.reset_source()
   await asyncio.sleep(2)
 async def pump():
  last=0
  while True:
   now=time.monotonic()
   for path in sorted(outbox.glob('*.json'))[:64]:
    try:
     if path.stat().st_size<2*1048576:relay.batch(json.loads(path.read_text()),now,time.time())
     else:relay.count['oversize_batch']+=1
    except FileNotFoundError:relay.count['outbox_file_races']+=1
    except (ValueError,KeyError,TypeError,OverflowError):relay.count['malformed_batch']+=1
    finally:path.unlink(missing_ok=True)
    publish(relay.ready(now))
   if now-last>1:
    tmp=a.runtime/'feed-status.tmp';tmp.write_text(json.dumps(relay.report(),indent=2)+'\n');tmp.replace(a.runtime/'feed-status.json');last=now
   await asyncio.sleep(.005)
 server=await asyncio.start_server(client,'127.0.0.1',a.port)
 async with server:await asyncio.gather(upstream(),pump(),server.serve_forever())
def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,default=Path('/run/readsb-dsp'));p.add_argument('--config',type=Path,default=Path('/etc/readsb-dsp/methods.json'));p.add_argument('--port',type=int,default=31005);p.add_argument('--stock-port',type=int,default=30005);p.add_argument('--worker-config',type=Path,default=Path('/etc/readsb-dsp/workers.json'));a=p.parse_args();asyncio.run(run(a))
if __name__=='__main__':main()

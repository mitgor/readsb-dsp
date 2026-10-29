"""Loopback-only, bounded Beast relay with conservative DSP insertion.

Every stock byte is retained, including unknown record types. A three-second
holdback permits ordered insertion; late experimental packets are dropped.
No connection is ever made to a readsb input port.
"""
import argparse,asyncio,bisect,heapq,json,math,os,time
from collections import Counter,deque
from pathlib import Path
from functools import lru_cache
from .wire import BeastParser
MOD=1<<48
CORRECTION=2398
ALLOWED={'energy','timing','soft','matched','coherent','sequence','acquisition','header','sic','neural','pulse'}
OPTIONAL={'header','sic','neural','pulse'}
@lru_cache(maxsize=20000)
def valid(payload):
    if not isinstance(payload,str) or len(payload)!=28:return False
    try:v=int(payload,16)
    except ValueError:return False
    if v>>107!=17:return False
    for b in range(111,23,-1):
        if v&(1<<b):v^=0x1fff409<<(b-24)
    return v==0

def beast(payload,ticks):
    # Signal amplitude was not calibrated in the DSP event: 0 means unavailable.
    body=(int(ticks)%MOD).to_bytes(6,'big')+b'\0'+bytes.fromhex(payload)
    return b'\x1a3'+body.replace(b'\x1a',b'\x1a\x1a')

def unwrap(tick,anchor):return anchor+((tick-anchor+MOD//2)%MOD-MOD//2)

class Records:
    """Lossless tokenizer: unknown bytes stay opaque; TCP splits are harmless."""
    def __init__(self):self.buffer=bytearray()
    def feed(self,chunk):
        self.buffer.extend(chunk);out=[];d=self.buffer;i=0;opaque=0
        while i+1<len(d):
            if d[i]!=26:i+=1;continue
            if d[i+1]==26:i+=2;continue
            n={49:9,50:14,51:21}.get(d[i+1])
            if n is None:i+=2;continue
            j=i+2;body=bytearray()
            while len(body)<n and j<len(d):
                b=d[j]
                if b==26:
                    if j+1>=len(d):break
                    if d[j+1]!=26:break
                    j+=1
                body.append(b);j+=1
            if len(body)<n:
                # Retain an incomplete record; malformed starts become opaque.
                if j<len(d)-1 and d[j]==26 and d[j+1]!=26:i+=2;continue
                break
            if i>opaque:out.append((bytes(d[opaque:i]),None))
            wire=bytes(d[i:j]);f=BeastParser().feed(wire)[0]
            out.append((wire,f));i=j;opaque=j
        if i>opaque:out.append((bytes(d[opaque:i]),None));opaque=i
        del d[:opaque]
        if len(d)>256:raise ValueError('Beast partial record exceeds bound')
        return out

class Relay:
    def __init__(self,holdback=3,config=None):
        self.config=Path(config) if config else None
        self.holdback=holdback;self.heap=[];self.seq=0;self.bytes=0;self.count=Counter();self.anchor=None;self.anchor_at=None;self.last_sent=-math.inf;self.stock_order_tick=-math.inf
        self.history=deque(maxlen=100000);self.accepted=deque(maxlen=50000);self.clients=set();self.connected=False;self.last_stock=0;self.started_unix=time.time();self.connected_since=None;self.upstream_error=None;self.connection_stock_base=0
    def push(self,tick,deadline,wire,source):
        self.seq+=1;heapq.heappush(self.heap,(tick,self.seq,deadline,wire,source));self.bytes+=len(wire)
        if self.bytes>16*1048576 or len(self.heap)>200000:raise RuntimeError('Stock relay buffer limit exceeded')
    def stock(self,wire,frame,now):
        if frame:
            tick=frame['ticks_12mhz'] if self.anchor is None else unwrap(frame['ticks_12mhz'],self.anchor)
            self.anchor=tick;self.anchor_at=now
            if frame['kind']==51 and valid(frame['message_hex']):self.history.append((tick,frame['message_hex']))
            self.count['stock_records_received']+=1
        else:tick=self.anchor or 0
        self.last_stock=now;self.count['stock_bytes_received']+=len(wire)
        self.stock_order_tick=max(tick,self.stock_order_tick)
        self.push(self.stock_order_tick,now+self.holdback,wire,'stock')
        while self.history and self.history[0][0]<tick-360000000:self.history.popleft()
        while self.accepted and self.accepted[0][0]<tick-120000000:self.accepted.popleft()
    def batch(self,batch,now,unix):
        if not batch.get('alignment',{}).get('verified') or not 0<=unix-batch.get('created_unix',0)<5:
            self.count['batch_rejected']+=1;return
        if self.anchor is None or now-self.last_stock>2:return
        known=list(self.history)+list(self.accepted)
        # A separate policy gate keeps expensive/experimental sources off the
        # feeder even if a stale worker sends an outbox batch after a toggle.
        from .pipeline import settings
        enabled=settings(self.config)
        for e in batch.get('extra',[])[:5000]:
            p=e.get('message_hex');source=e.get('source')
            if source not in ALLOWED or not valid(p):self.count['policy_rejected']+=1;continue
            if source in OPTIONAL and not enabled[source]:self.count['disabled_source_rejected']+=1;continue
            t=unwrap((int(e['ticks'])+CORRECTION)%MOD,self.anchor)
            deadline=self.anchor_at+(t-self.anchor)/12000000+self.holdback
            if abs(t-self.anchor)>60000000 or t<=self.last_sent or deadline<=now:
                self.count['late_rejected']+=1;continue
            if any(q==p and abs(s-t)<=1440 for s,q in known):self.count['duplicates_rejected']+=1;continue
            if not any(q[2:8]==p[2:8] and t-360000000<=s<=t for s,q in self.history):
                self.count['no_prior_stock_rejected']+=1;continue
            if any(q[2:8]==p[2:8] and q!=p and abs(s-t)<=48 for s,q in self.history):
                self.count['conflict_rejected']+=1;continue
            self.accepted.append((t,p));known.append((t,p));self.push(t,deadline,beast(p,t),source);self.count['accepted_'+source]+=1
    def ready(self,now):
        out=[]
        while self.heap and self.heap[0][2]<=now:
            tick,seq,deadline,wire,source=heapq.heappop(self.heap);self.bytes-=len(wire)
            if source!='stock':
                f=BeastParser().feed(wire)[0];payload=f['message_hex']
                if any(q==payload and abs(s-tick)<=1440 for s,q in self.history):
                    self.count['late_stock_duplicates_rejected']+=1;continue
                if any(q[2:8]==payload[2:8] and q!=payload and abs(s-tick)<=48 for s,q in self.history):
                    self.count['late_stock_conflicts_rejected']+=1;continue
            self.last_sent=max(tick,self.last_sent);self.count['stock_bytes_relayed' if source=='stock' else 'dsp_frames_relayed']+=len(wire) if source=='stock' else 1
            if source!='stock':self.count['relayed_'+source]+=1
            out.append(wire)
        return b''.join(out)
    def reset_source(self):
        # Only after the old holdback has drained. Do not mix receiver epochs.
        if self.heap:raise RuntimeError('Cannot reset a nonempty stock buffer')
        self.anchor=None;self.anchor_at=None;self.last_sent=-math.inf;self.stock_order_tick=-math.inf;self.history.clear();self.accepted.clear()
    def report(self):
        from .pipeline import settings
        enabled=settings(self.config)
        return {'current_connection_stock_bytes_relayed':self.count['stock_bytes_relayed']-self.connection_stock_base,'pid':os.getpid(),'started_unix':self.started_unix,'upstream_connected_since_unix':self.connected_since,'upstream_error':self.upstream_error,'last_stock_age_s':None if not self.last_stock else time.monotonic()-self.last_stock,'updated_unix':time.time(),'mode':'stock_plus_validated_dsp','holdback_s':self.holdback,'stock_connected':self.connected,'clients':len(self.clients),'buffer_bytes':self.bytes,'counts':dict(self.count),'allowed_sources':sorted(ALLOWED-OPTIONAL|{s for s in OPTIONAL if enabled[s]}),'optional_sources_available':sorted(OPTIONAL),'fr24_routed':Path('/run/adsb-rescue/feed-routing.json').exists(),'neural_enabled':enabled['neural'],'broad_crc_forwarded':False}

async def run(a):
    relay=Relay(a.holdback,a.config);outbox=a.runtime/'feed-outbox';outbox.mkdir(exist_ok=True)
    async def client(reader,writer):
        relay.clients.add(writer)
        try:
            while await reader.read(4096):pass
        finally:relay.clients.discard(writer);writer.close()
    async def upstream():
        while True:
            writer=None;parser=Records()
            try:
                reader,writer=await asyncio.wait_for(asyncio.open_connection('127.0.0.1',getattr(a,'stock_port',30005)),10)
                relay.connection_stock_base=relay.count['stock_bytes_relayed'];relay.connected=True;relay.connected_since=time.time();relay.upstream_error=None;relay.count['upstream_connections']+=1
                while True:
                    try:raw=await asyncio.wait_for(reader.read(65536),getattr(a,'idle_timeout',15))
                    except asyncio.TimeoutError:
                        # No aircraft/messages is normal. The status pump and
                        # downstream stock socket remain alive during silence.
                        relay.count['stock_idle_timeouts']+=1;continue
                    if not raw:raise ConnectionError('Stock source disconnected')
                    for wire,frame in parser.feed(raw):relay.stock(wire,frame,time.monotonic())
            except (OSError,asyncio.TimeoutError) as e:
                relay.count['upstream_disconnects']+=1;relay.upstream_error=type(e).__name__+': '+str(e)
            finally:
                relay.connected=False;relay.connected_since=None
                if writer:
                    writer.close()
                    try:await writer.wait_closed()
                    except OSError:pass
            # Preserve buffered stock bytes, including an opaque final fragment,
            # before reconnecting. Reset downstream parsers at connection epochs.
            if parser.buffer:relay.stock(bytes(parser.buffer),None,time.monotonic())
            while relay.heap:await asyncio.sleep(.05)
            for downstream in list(relay.clients):downstream.close()
            relay.clients.clear();relay.reset_source()
            await asyncio.sleep(getattr(a,'reconnect_delay',2))
    async def pump():
        last=0
        while True:
            a.runtime.mkdir(parents=True,exist_ok=True);outbox.mkdir(exist_ok=True)
            now=time.monotonic()
            for path in sorted(outbox.glob('*.json')):
                try:
                    if path.stat().st_size<2*1048576:relay.batch(json.loads(path.read_text()),now,time.time())
                    else:relay.count['oversize_batch']+=1
                except FileNotFoundError:relay.count['outbox_file_races']+=1
                except (ValueError,KeyError,TypeError,OverflowError):relay.count['malformed_batch']+=1
                finally:path.unlink(missing_ok=True)
            raw=relay.ready(now)
            if raw:
                for writer in list(relay.clients):
                    try:
                        writer.write(raw);await asyncio.wait_for(writer.drain(),.5)
                        relay.count['client_bytes_sent']+=len(raw)
                    except (ConnectionError,asyncio.TimeoutError):relay.clients.discard(writer);writer.close();relay.count['slow_clients_closed']+=1
            if now-last>1:
                temp=a.runtime/'feed-status.tmp';temp.write_text(json.dumps(relay.report(),indent=2)+'\n');temp.replace(a.runtime/'feed-status.json');last=now
            await asyncio.sleep(.02)
    server=await asyncio.start_server(client,'127.0.0.1',a.port)
    async with server:await asyncio.gather(upstream(),pump(),server.serve_forever())

def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,default=Path('/run/adsb-rescue'));p.add_argument('--config',type=Path,default=Path('/etc/default/adsb-rescue.json'));p.add_argument('--port',type=int,default=31005);p.add_argument('--holdback',type=float,default=3);a=p.parse_args()
    if not 2<=a.holdback<=5:p.error('holdback must be 2–5 seconds')
    asyncio.run(run(a))
if __name__=='__main__':main()

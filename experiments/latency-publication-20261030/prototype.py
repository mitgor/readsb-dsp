"""Isolated latency experiment. No sockets, outbox writes, or production imports/hooks.

Keep one-second statistics/training output unchanged while tapping completed DSP
batches. Stock watermarks and a rolling alignment audit fail closed. All outputs
remain experiment-only until prospective parity and FR24 cloud review.
"""
from collections import Counter, deque
from rescue.feed import Relay, beast, valid, unwrap, MOD, CORRECTION, ALLOWED
from rescue.shadow import evaluate
from rescue.streaming import StreamingPool, HALO, CORE
from rescue.workers import merge_events

class BatchTap:
    """Mixin used ONLY by experiment pool subclasses, including shared-ring pools."""
    def _assemble(self,batch,rows,work):
        if not hasattr(self,'early_batches'):
            self.early_batches=deque(maxlen=32);self.early_dropped=0
        if len(self.early_batches)==self.early_batches.maxlen:self.early_dropped+=1
        # Own rows, preserving source precedence and exact sample positions.
        self.early_batches.append((batch,merge_events([rows]),dict(work)))
        return super()._assemble(batch,rows,work)
    def pop_batches(self):
        result=list(getattr(self,'early_batches',()));getattr(self,'early_batches',deque()).clear();return result

class SmallBatchGate:
    """Same admission function as production, using causal rolling energy anchors.

    No extrapolated clock/ICAO and no learned labels. A stock-progress watermark
    must cover a batch before evaluation; after 250ms it is dropped, never waited
    on indefinitely. This may lose extras; parity must be measured before use.
    """
    def __init__(self,max_age=.250,capacity=32):
        self.max_age=max_age;self.capacity=capacity;self.pending=deque();self.energy=deque();self.epoch=None;self.count=Counter();self.last_first=None
    def offer(self,batch,rows,now):
        if batch.epoch!=self.epoch:
            self.pending.clear();self.energy.clear();self.epoch=batch.epoch;self.last_first=None;self.count['epoch_reset']+=1
        start=max((batch.first+HALO)*5,(batch.first+batch.bounds[0]*120000)*5)
        end=min((batch.first+HALO+CORE)*5,(batch.first+batch.bounds[1]*120000)*5)
        if self.last_first is not None and start<self.last_first:self.count['out_of_order_batch']+=1;return
        self.last_first=start
        events=[{**r,'ticks':batch.first*5+r['sample_4msps']*3} for r in rows]
        # Include same-second halo anchors for alignment, but only own core events
        # are ever emitted. Across windows keep at most one RF second of anchors.
        self.energy.extend(r for r in events if r['source']=='energy')
        cutoff=end-12000000
        self.energy=deque((r for r in self.energy if r['ticks']>=cutoff),maxlen=10000)
        if len(self.pending)>=self.capacity:self.pending.popleft();self.count['overflow_dropped']+=1
        self.pending.append((start,end,events,now))
    def drain(self,frames,now,epoch,stock_watermark,enabled):
        if epoch!=self.epoch:self.count['wrong_epoch']+=1;return []
        out=[]
        while self.pending:
            start,end,events,created=self.pending[0]
            if now-created>self.max_age:self.pending.popleft();self.count['expired_batch']+=1;continue
            if stock_watermark is None or stock_watermark<end:self.count['await_stock_progress']+=1;break
            self.pending.popleft()
            # Do not use anchors from a later not-yet-settled batch.
            anchors=[r for r in self.energy if end-12000000<=r['ticks']<end]
            current=[r for r in events if start<=r['ticks']<end and enabled.get(r['source'],False)]
            extras,audit,decisions=evaluate(frames,anchors+[r for r in current if r['source']!='energy'],start,end)
            self.count.update(decisions)
            if not audit['verified']:self.count['alignment_not_ready']+=1;continue
            # evaluate includes rolling anchors for validation, never forward the
            # previous batch again. No age/timestamp mutation or novel CRC gate.
            out.append(dict(epoch=epoch,alignment=audit,extra=[r for r in extras if start<=r['ticks']<end and enabled.get(r['source'],False)],created_monotonic=created))
        return out

class ImmediateRelay(Relay):
    """Single-emitter experimental relay: stock has zero intentional holdback.

    Five-second shared transmission cache; no payload-only suppression. Every
    stock byte survives, including late stock. Original Beast timestamps remain.
    """
    def __init__(self,history_class,allowed_sources=None,**kwargs):
        super().__init__(holdback=0,**kwargs);self.cache=history_class();self.epoch=None
        self.allowed_sources=set(ALLOWED if allowed_sources is None else allowed_sources)
    def stock(self,wire,frame,now,epoch=None):
        if epoch is not None and epoch!=self.epoch:
            if self.heap:raise RuntimeError('Drain previous epoch before reset')
            self.reset_source();self.epoch=epoch;self.cache.reset(epoch)
        # Base retains stock identity/conflict guards and opaque bytes.
        super().stock(wire,frame,now)
        if frame and frame['kind']==51:
            self.cache.push('stock',self.epoch,self.anchor,frame['message_hex'],now,validated=True)
    def batch(self,batch,now,unix,enabled=None):
        if enabled is None:raise ValueError('Explicit current method switches required')
        if batch.get('epoch')!=self.epoch or not batch.get('alignment',{}).get('verified'):
            self.count['batch_rejected']+=1;return
        if not 0<=unix-batch.get('created_unix',0)<.250 or self.anchor is None or now-self.last_stock>2:
            self.count['stale_batch_rejected']+=1;return
        for e in batch.get('extra',[])[:5000]:
            p=e.get('message_hex');source=e.get('source')
            if source not in self.allowed_sources or not enabled.get(source,False) or not valid(p):self.count['policy_rejected']+=1;continue
            t=unwrap((int(e['ticks'])+CORRECTION)%MOD,self.anchor)
            # Compare RF age against causal stock sample clock, not CPU wall time.
            if not 0<=self.anchor-t<=3000000:self.count['rf_age_rejected']+=1;continue
            if not any(q[2:8]==p[2:8] and t-360000000<=s<=t for s,q in self.history):self.count['no_prior_stock_rejected']+=1;continue
            if any(q[2:8]==p[2:8] and q!=p and abs(s-t)<=48 for s,q in self.history):self.count['conflict_rejected']+=1;continue
            if not self.cache.push(source,self.epoch,t,p,now,validated=True):self.count['duplicates_rejected']+=1;continue
            self.accepted.append((t,p));self.push(t,now,beast(p,t),source);self.count['accepted_'+source]+=1
    def ready(self,now):
        # No timestamp sorting of stock vs extras: serialize arrival sequence.
        pending=sorted(self.heap,key=lambda r:r[1]);self.heap=[];out=[]
        for tick,seq,deadline,wire,source in pending:
            self.bytes-=len(wire)
            if source!='stock':
                from rescue.wire import BeastParser
                p=BeastParser().feed(wire)[0]['message_hex']
                if any(q==p and abs(s-tick)<=1440 for s,q in self.history):self.count['late_stock_duplicates_rejected']+=1;continue
                if any(q[2:8]==p[2:8] and q!=p and abs(s-tick)<=48 for s,q in self.history):self.count['late_stock_conflicts_rejected']+=1;continue
            self.count['stock_bytes_relayed' if source=='stock' else 'dsp_frames_relayed']+=len(wire) if source=='stock' else 1
            out.append(wire)
        return b''.join(out)

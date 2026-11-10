from .feed import Relay,beast,valid,unwrap,MOD,CORRECTION,ALLOWED
class ImmediateRelay(Relay):
    """Single-emitter experimental relay: stock has zero intentional holdback.

    Five-second shared transmission cache; no payload-only suppression. Every
    stock byte survives, including late stock. Original Beast timestamps remain.
    """
    def __init__(self,history_class,allowed_sources=None,max_extra_age=.250,**kwargs):
        super().__init__(holdback=0,**kwargs);self.cache=history_class();self.epoch=None
        self.allowed_sources=set(ALLOWED if allowed_sources is None else allowed_sources)
        if not .05<=max_extra_age<=5:raise ValueError('Experimental extra age must be .05–5seconds')
        self.max_extra_age=max_extra_age
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
        if not 0<=unix-batch.get('created_unix',0)<self.max_extra_age or self.anchor is None or now-self.last_stock>2:
            self.count['stale_batch_rejected']+=1;return
        for e in batch.get('extra',[])[:5000]:
            p=e.get('message_hex');source=e.get('source')
            if source not in self.allowed_sources or not enabled.get(source,False) or not valid(p):self.count['policy_rejected']+=1;continue
            t=unwrap((int(e['ticks'])+CORRECTION)%MOD,self.anchor)
            # Compare RF age against causal stock sample clock, not CPU wall time.
            if not 0<=self.anchor-t<=self.max_extra_age*12000000:self.count['rf_age_rejected']+=1;continue
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
            if source!='stock':self.count['relayed_'+source]+=1
            out.append(wire)
        return b''.join(out)

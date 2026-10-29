"""100 ms dispatch, unchanged 50 ms DSP blocks and one-second comparisons.

Copied IQ and jobs stay bounded in RAM. No receiver or feeder ownership.
"""
from collections import deque
from dataclasses import dataclass
import os,time
from .workers import WorkerPool,decode_job,merge_events
RATE=2400000
CORE=RATE
HALO=600
TOTAL=CORE+2*HALO
HOP=120000

@dataclass
class Batch:
    epoch:int
    first:int
    wall:float
    raw:bytes
    bounds:tuple
    raw_start:int
    queued:float
    whole_raw:bytes|None=None

class Assembler:
    """Emit available blocks immediately, retaining original RF-window edges."""
    def __init__(self,dispatch_ms=100):
        if dispatch_ms not in (50,100):raise ValueError('Dispatch must be 50 or 100 ms')
        self.dispatch_ms=dispatch_ms;self.blocks=dispatch_ms//50
        self.buf=bytearray();self.expected=None;self.epoch=None;self.first=0;self.wall=0.;self.next_block=0;self.discontinuities=0
    def feed(self,epoch,sample,wall,raw):
        if len(raw)%2:raise ValueError('Truncated I/Q')
        if epoch!=self.epoch or sample!=self.expected:
            self.buf.clear();self.next_block=0;self.discontinuities+=1
            skip=(-sample)%3;self.first=sample+skip;self.wall=wall+skip/RATE;self.epoch=epoch
            data=raw[skip*2:]
        else:data=raw
        self.expected=sample+len(raw)//2;self.buf.extend(data);out=[]
        while True:
            lo=self.next_block;hi=min(20,lo+self.blocks)
            if hi==20:hi=21 # Preserve the original short trailing halo block.
            raw_start=max(0,lo*HOP-HALO);raw_end=min(TOTAL,hi*HOP+HALO)
            if len(self.buf)<raw_end*2:break
            final=hi==21
            out.append(Batch(epoch,self.first,self.wall,bytes(self.buf[raw_start*2:raw_end*2]),(lo,hi),raw_start,time.monotonic(),bytes(self.buf[:TOTAL*2]) if final else None))
            self.next_block=hi
            if final:
                del self.buf[:CORE*2];self.first+=CORE;self.wall+=1;self.next_block=0
        return out

class StreamingPool(WorkerPool):
    def __init__(self,*args,dispatch_ms=100,settle_s=.5,**kwargs):
        super().__init__(*args,**kwargs)
        self.dispatch_ms=dispatch_ms;self.settle_s=settle_s;self.max_pending_jobs=self.selection['workers']*2
        self.group=None;self.finished=deque();self.incomplete_groups=0;self.completed_seconds=0;self.batch_latencies=deque(maxlen=1200)
    def submit(self,batch,stock=()):
        if len(self.pending)>=self.max_pending_jobs:raise RuntimeError('Bounded streaming pool full')
        lo,hi=batch.bounds;count=min(self.selection['workers'],hi-lo)
        ranges=[(lo+i*(hi-lo)//count,lo+(i+1)*(hi-lo)//count) for i in range(count)]
        path=self.runtime/f'job-{os.getpid()}-{self.jobs}.uc8'
        path.write_bytes(batch.raw);self.job_paths.add(path);submitted=time.monotonic()
        tasks=self.submit_ranges(path,ranges,stock,batch.raw_start,TOTAL)
        self.pending.append((batch,tasks,submitted,path));self.jobs+=1
    def _assemble(self,batch,rows,work):
        key=(batch.epoch,batch.first)
        if self.group is not None and self.group['key']!=key:
            self.incomplete_groups+=1;self.group=None
        if self.group is None:
            if batch.bounds[0]!=0:return
            self.group=dict(key=key,expected=0,rows=[],work=[],first_batch=batch)
        g=self.group
        if batch.bounds[0]!=g['expected']:
            self.incomplete_groups+=1;self.group=None;return
        g['rows'].append(rows);g['work'].append(work);g['expected']=batch.bounds[1]
        self.batch_latencies.append(work['result_latency_s'])
        if batch.bounds[1]!=21:return
        if batch.whole_raw is None:raise ValueError('Final batch missing training window')
        events=self.combine_events(g['rows']);combined={}
        for detail in g['work']:
            for name,value in detail.items():
                if name in ('outputs','worker_pid','worker_pids','chunks','job_wall_s','result_latency_s','parallel_overlap_s'):continue
                if isinstance(value,(int,float)):
                    combined[name]=max(combined.get(name,0),value) if name=='max_block_s' else combined.get(name,0)+value
        combined.update(outputs=len(events),job_wall_s=sum(d['execution_span_s'] for d in g['work']),
            result_latency_s=time.monotonic()-g['first_batch'].queued,
            mean_batch_latency_s=sum(d['result_latency_s'] for d in g['work'])/len(g['work']),
            max_batch_latency_s=max(d['result_latency_s'] for d in g['work']),
            dispatch_ms=self.dispatch_ms,chunks=[c for d in g['work'] for c in d['chunks']])
        item=(batch.epoch,batch.first,batch.wall,batch.whole_raw,g['first_batch'].queued)
        # Let stock Beast output catch up before comparison, not before DSP.
        if len(self.finished)>=2:
            self.finished.popleft();self.incomplete_groups+=1
        self.finished.append((batch.queued+self.settle_s,(item,events,combined)))
        self.group=None;self.completed_seconds+=1
    def combine_events(self,parts):return merge_events(parts)
    def pop(self):
        while super().ready():
            batch,rows,work=super().pop(raw_events=True);self._assemble(batch,rows,work)
        if self.finished and time.monotonic()>=self.finished[0][0]:return self.finished.popleft()[1]
        return None
    def report(self):
        return {**super().report(),'dispatch_ms':self.dispatch_ms,'chunking':'streaming_50ms_blocks',
            'max_pending_jobs':self.max_pending_jobs,'max_pending_chunks':self.max_pending_jobs*self.selection['workers']*(2 if getattr(self,'coherent_executor',None) else 1),
            'coherent_workers':len(self.selection.get('coherent_cpus',[])) if getattr(self,'coherent_executor',None) else 0,
            'pending_comparisons':len(self.finished),'comparison_settle_s':self.settle_s,
            'completed_rf_seconds':self.completed_seconds,'incomplete_rf_seconds_shed':self.incomplete_groups,
            'mean_batch_latency_s':sum(self.batch_latencies)/len(self.batch_latencies) if self.batch_latencies else None,
            'max_recent_batch_latency_s':max(self.batch_latencies,default=None)}


def make_streaming_pool(model,methods,runtime,selection,**kwargs):
    if selection.get('config',{}).get('shared_transport','files')=='ring':
        from .ring_transport import RingStreamingPool
        return RingStreamingPool(model,methods,runtime,selection,**kwargs)
    return StreamingPool(model,methods,runtime,selection,**kwargs)

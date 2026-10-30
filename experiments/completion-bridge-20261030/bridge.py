"""Experiment only: completion-future admission independent of grouping/collection."""
from collections import Counter, deque
from rescue.shadow import evaluate
from rescue.streaming import HALO, CORE
from rescue.workers import merge_events
from rescue.stock_history import StockHistory

class CompletionPool:
    def pop(self):
        if not hasattr(self,'completed_methods'):
            self.completed_methods=deque();self.completion_seen=set()
        live=set()
        for batch,tasks,submitted,path in self.pending:
            for task in tasks:
                live.add(task)
                if task in self.completion_seen or not task.done():continue
                self.completion_seen.add(task)
                rows,work=task.result()
                self.completed_methods.append((batch,[dict(r) for r in rows],dict(work)))
        self.completion_seen.intersection_update(live)
        return super().pop()
    def take_completed(self):
        result=list(getattr(self,'completed_methods',()))
        if hasattr(self,'completed_methods'):self.completed_methods.clear()
        return result

class Bridge:
    def __init__(self,enabled,max_age=3.,capacity=256):
        self.enabled=dict(enabled);self.max_age=max_age;self.capacity=capacity
        self.pending=deque();self.energy={};self.seen={};self.count=Counter();self.epoch=None;self.energy_generation=0
    def begin_epoch(self,epoch):
        # Caller observes the original RF input epoch; late old futures cannot
        # switch admission back into a previous receiver session.
        self.pending.clear();self.energy.clear();self.seen.clear();self.epoch=epoch;self.count['epoch_reset']+=1
    def offer(self,batch,rows,now):
        if self.epoch is None:self.begin_epoch(batch.epoch)
        if self.epoch!=batch.epoch:
            self.count['wrong_epoch']+=1;return
        start=max((batch.first+HALO)*5,(batch.first+batch.bounds[0]*120000)*5)
        end=min((batch.first+HALO+CORE)*5,(batch.first+batch.bounds[1]*120000)*5)
        events=[dict(r,ticks=batch.first*5+r['sample_4msps']*3) for r in rows if r['source']!='broad_crc']
        for r in events:
            if r['source']=='energy':self.energy[(r['ticks'],r['message_hex'])]=r;self.energy_generation+=1
        if len(self.pending)>=self.capacity:self.count['overflow']+=1;return
        self.pending.append((start,end,events,now,batch,None))
    def drain(self,frames,watermark,now,rf_now):
        out=[];remaining=deque()
        if watermark is None:return []
        cutoff=min([watermark-12000000]+[p[1]-12000000 for p in self.pending])
        self.energy={k:r for k,r in self.energy.items() if r['ticks']>=cutoff}
        if len(self.energy)>40000:
            self.count['anchor_capacity_fail_closed']+=1;self.pending.clear();self.energy.clear();return []
        self.seen={p:[s for s in times if s>=watermark-60000000] for p,times in self.seen.items() if times and max(times)>=watermark-60000000}
        token=(id(frames),watermark,self.energy_generation)
        for start,end,events,created,batch,previous in self.pending:
            if now-created>self.max_age:self.count['pending_expired']+=len(events);continue
            if watermark<end:
                remaining.append((start,end,events,created,batch,token));self.count['watermark_wait']+=1;continue
            if previous==token:
                remaining.append((start,end,events,created,batch,token));continue
            anchors=[r for r in self.energy.values() if end-12000000<=r['ticks']<end]
            current=[r for r in events if start<=r['ticks']<end and self.enabled.get(r['source'],False)]
            # Future chunks cannot authorize alignment of an earlier chunk.
            extras,audit,decisions=evaluate(frames,anchors+[r for r in current if r['source']!='energy'],start,end)
            if not audit['verified']:
                remaining.append((start,end,events,created,batch,token));self.count['alignment_wait']+=1;continue
            self.count.update(decisions)
            for r in extras:
                if not start<=r['ticks']<end or not self.enabled.get(r['source'],False):continue
                p=r['message_hex'];t=r['ticks'];times=self.seen.setdefault(p,[])
                if any(abs(s-t)<=1440 for s in times):self.count['shared_duplicate']+=1;continue
                age=(rf_now-t)/12000000
                if age<0:self.count['future_rejected']+=1;continue
                if age>self.max_age:self.count['rf_expired']+=1;continue
                times.append(t);out.append(dict(r,emitted=now,rf_age_s=age,batch_first=batch.first,epoch=batch.epoch,alignment=audit));self.count['emitted_'+r['source']]+=1
        self.pending=remaining
        return out

def publish_to(hub,rows,created_unix):
    """Optional isolated AsyncFanIn sink; no socket/config/production ownership.

    Each admitted row is queued independently. Fan-in rechecks switches, epoch,
    freshness and stock identity. Queue refusal stays explicit; do not retry by
    rewriting an RF timestamp. The benchmark measures pre-transport admission.
    """
    counts=Counter()
    for r in rows:
        source=r['source']
        batch=dict(epoch=r['epoch'],created_unix=created_unix,
                   admission='production_guarded_v1',alignment=dict(r['alignment']),
                   extra=[{k:r[k] for k in ('message_hex','ticks','source')}])
        counts['queued' if hub.submit(source,batch) else 'queue_refused']+=1
    return dict(counts)

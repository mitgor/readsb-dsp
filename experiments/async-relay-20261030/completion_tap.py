"""Experiment-only per-future candidate tap, no forwarding or admission bypass.

A slow coherent future never withholds completed cheap DSP candidates. Original
pool still waits for the full group for its existing statistics/collection path.
Fused native branches report together; do not recompute their shared frontend.
"""
from collections import Counter,deque
class CompletionTap:
 def pop(self):
  if not hasattr(self,'method_results'):
   self.method_results=deque(maxlen=2048);self.method_seen=set();self.method_count=Counter()
  live=set()
  for batch,tasks,submitted,path in self.pending:
   for task in tasks:
    live.add(task)
    if task in self.method_seen or not task.done():continue
    self.method_seen.add(task);rows,work=task.result();by={}
    for row in rows:by.setdefault(row['source'],[]).append(dict(row))
    for source,events in by.items():
     if len(self.method_results)==self.method_results.maxlen:self.method_count['queue_overflow']+=1
     self.method_results.append(dict(epoch=batch.epoch,first=batch.first,source=source,events=events,queued=batch.queued,work=work,admitted=False))
  self.method_seen.intersection_update(live)
  return super().pop()
 def pop_methods(self):
  out=list(getattr(self,'method_results',()));getattr(self,'method_results',deque()).clear();return out

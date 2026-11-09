"""Completion tap that cannot miss a future consumed during the normal pop call."""
from collections import deque,Counter
class CompletionPool:
 def collect(self,records):
  if not hasattr(self,'completed_methods'):self.completed_methods=deque(maxlen=4096);self.completion_seen=set();self.completion_counts=Counter()
  for batch,tasks,submitted,path in records:
   for task in tasks:
    if task in self.completion_seen or not task.done():continue
    rows,work=task.result();self.completion_seen.add(task)
    if len(self.completed_methods)==self.completed_methods.maxlen:self.completion_counts['overflow']+=1
    self.completed_methods.append((batch,[dict(r) for r in rows],dict(work)))
 def pop(self):
  # Keep references to futures: normal grouping may remove them while running.
  before=list(self.pending);self.collect(before);result=super().pop();self.collect(before);self.collect(list(self.pending))
  self.completion_seen.intersection_update({task for b,tasks,s,p in self.pending for task in tasks});return result
 def take_completed(self):
  result=list(getattr(self,'completed_methods',()));self.completed_methods.clear();return result

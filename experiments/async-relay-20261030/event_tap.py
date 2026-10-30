"""Optional experiment callback at runtime event creation; no admission/forwarding.
Energy candidates can be observed before neural/classical processing finishes.
Callback failures/overflow never change decoder output. Later annotations may not
be present yet; these provisional rows are never training labels or feeder input.
"""
from collections import Counter
class EventTap:
 def __init__(self,decoder,publish):
  self.decoder=decoder;self.publish=publish;self.original=decoder._event;self.count=Counter()
  def event(events,*args):
   before=len(events);result=self.original(events,*args)
   for row in events[before:]:
    try:
     accepted=self.publish({**row,'admitted':False})
     self.count['queue_full' if accepted is False else 'published']+=1
    except Exception:self.count['callback_failed']+=1
   return result
  self.wrapper=event;decoder._event=event
 def close(self):
  if self.decoder._event is self.wrapper:self.decoder._event=self.original

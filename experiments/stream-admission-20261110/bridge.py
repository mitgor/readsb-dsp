"""Isolated causal energy/Stream admission with a no-redecode finalization lane.
Never reads production sockets/configuration or writes production outboxes.
"""
from collections import Counter
from rescue.stream1090_shadow import compare,valid_df17
from indexed import evaluate_subset as evaluate

class Bridge:
 def __init__(self,epoch,emit,early=True):
  self.early=early;self.epoch=epoch;self.emit=emit;self.windows={};self.count=Counter();self.energy=[]
 def begin(self,key,case):
  assert key not in self.windows
  self.windows[key]={'case':case,'native':[],'energy':[],'native_watermark':-1,'energy_watermark':-1,'native_done':False,'energy_done':False,'offset':None,'slice':0,'finalized':False}
 def offer(self,key,source,epoch,rows,watermark,done):
  if epoch!=self.epoch:self.count['wrong_epoch']+=len(rows);return
  w=self.windows[key]
  if w['finalized']:self.count['late_result']+=len(rows);return
  if source not in ['native','energy']:raise ValueError('Unknown producer')
  if any(not valid_df17(r[1] if source=='native' else r['message_hex']) for r in rows):raise ValueError('Invalid CRC candidate')
  w[source]+=rows;w[source+'_watermark']=max(w[source+'_watermark'],watermark);w[source+'_done']|=done
  if source=='energy':self.energy+=rows
 def _clock(self,w,frames):
  c=w['case'];start=(c['first']+600)*5;end=start+12000000
  if hasattr(frames,'payloads'):
   stock=[(t,p) for p in {m for t,m in w['native']} for t in frames.payloads.get(p,()) if start-60000<=t<end+60000]
  else:stock=[(r['ticks'],r['message_hex']) for r in frames if start-60000<=r['ticks']<end+60000]
  audit,extras=compare(w['native'],stock)
  if audit['aligned']:
   if w['offset'] is None:w['offset']=audit['offset_ticks'];self.count['clock_ready']+=1
   elif abs(w['offset']-audit['offset_ticks'])>24:
    self.count['clock_shift_after_ready']+=1;return None
   return audit,extras
  return None
 def drain(self,frames,stock_watermark,now):
  if stock_watermark is None:return
  for key,w in self.windows.items():
   if w['finalized']:continue
   c=w['case'];start=(c['first']+600)*5;end=start+12000000
   final_ready=w['native_done'] and w['energy_done'] and stock_watermark>=end+1440
   next_end=min(end,start+(w['slice']+1)*240000)
   early_ready=self.early and w['slice']<50 and min(w['native_watermark'],w['energy_watermark'],stock_watermark)>=next_end+1440
   if not (final_ready or early_ready):continue
   # Once established, sample-clock mapping is fixed for this logical window.
   # Recheck against the complete available reference at finalization.
   clock=self._clock(w,frames) if w['offset'] is None or final_ready else (True,[])
   if clock and early_ready:
    # Both producer watermarks must cover a slice before early admission. No
    # future RF anchors or missing producer completions authorize an early row.
    while w['slice']<50:
     lo=start+w['slice']*240000;hi=min(end,lo+240000)
     if min(w['native_watermark'],w['energy_watermark'],stock_watermark)<hi+1440:break
     anchors=[r for r in self.energy if hi-12000000<=r['ticks']<hi]
     events=[{'source':'stream1090','ticks':t+w['offset'],'message_hex':m} for t,m in w['native'] if lo<=t+w['offset']<hi]
     # The production function is unchanged: energy audit, stock-only prior
     # identity, CRC, conflict and 120us duplicate checks all remain.
     out,audit,decisions=evaluate(frames,anchors+events,lo,hi)
     if audit['verified']:
      self.count.update(decisions)
      for r in out:
       if lo<=r['ticks']<hi:self.emit(r,audit,now,'early')
     else:self.count['early_alignment_not_ready']+=1
     w['slice']+=1
   # Late lane reuses raw decoder results, never RF reprocessing. It is needed
   # for cold-start clock/energy evidence that cannot authorize earlier slices.
   if final_ready:
    if clock:
     out,audit,decisions=evaluate(frames,w['energy']+[{'source':'stream1090','ticks':t,'message_hex':m} for t,m in clock[1] if start<=t<end],start,end)
     self.count.update({'final_'+k:v for k,v in decisions.items()})
     if audit['verified']:
      for r in out:
       if start<=r['ticks']<end:self.emit(r,audit,now,'final')
     else:self.count['final_alignment_not_ready']+=1
    else:self.count['final_clock_not_ready']+=1
    w['finalized']=True;self.count['finalized_windows']+=1
 def pending(self):return sum(not w['finalized'] for w in self.windows.values())

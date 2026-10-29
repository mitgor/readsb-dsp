"""Conservative pulse-only increments over stock, accepted DSP and actual relay."""
from bisect import bisect_left
from collections import Counter,defaultdict
from .shadow import valid_df17
TOL=1440

def index(rows):
 out=defaultdict(list)
 for r in rows:out[r['message_hex']].append(r['ticks'])
 for v in out.values():v.sort()
 return out

def nearby(mapping,p,t,tolerance=TOL):
 times=mapping.get(p,());i=bisect_left(times,t-tolerance)
 return i<len(times) and times[i]<=t+tolerance

def compare(candidates,stock,unified,base):
 """Caller verifies epoch, clock alignment and complete/live comparison streams.

 Stock-only identity guard is causal (prior <=30s), distinct transmissions use
 sample timestamps, and accepted DSP candidates mask relay delivery failures.
 """
 stock_index=index(stock);relay_index=index(unified);base_index=index(base)
 identities=defaultdict(list)
 for r in stock:identities[r['message_hex'][2:8]].append((r['ticks'],r['message_hex']))
 selected={};counts=Counter();added=[]
 for r in sorted(candidates,key=lambda r:r['ticks']):
  p=r['message_hex'];t=r['ticks'];counts['pulse_valid_candidates']+=1
  if not valid_df17(p):counts['invalid_crc_or_df']+=1;continue
  if nearby(stock_index,p,t):counts['already_stock']+=1;continue
  prior=identities.get(p[2:8],())
  if not any(t-360000000<=s<=t for s,q in prior):counts['no_prior_stock_icao']+=1;continue
  if any(abs(s-t)<=48 and q!=p for s,q in prior):counts['stock_conflict']+=1;continue
  if any(q['message_hex']!=p and q['message_hex'][2:8]==p[2:8] and abs(q['ticks']-t)<=48 for q in candidates):counts['pulse_conflict']+=1;continue
  if nearby(relay_index,p,t):counts['already_actual_pipeline']+=1;continue
  if nearby(base_index,p,t):counts['already_accepted_dsp']+=1;continue
  if nearby(selected,p,t):counts['pulse_duplicate']+=1;continue
  selected.setdefault(p,[]).append(t);added.append(r);counts['pulse_on_top']+=1
 return added,dict(counts)

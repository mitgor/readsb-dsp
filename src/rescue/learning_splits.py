"""Keep evaluation IQ membership and order fixed across daily training runs."""
def freeze_evaluation(sets,manifest):
 result={name:list(rows) for name,rows in sets.items()};excluded={}
 for name in ('validation','test'):
  required=manifest['splits'][name]['sha256']
  if len(required)!=len(set(required)):raise ValueError('Duplicate frozen evaluation IQ')
  available={row[5]:row for row in result[name]};missing=set(required)-set(available)
  if missing:raise ValueError(f'{name}: {len(missing)} frozen evaluation windows missing after provenance/RF checks; do not substitute new test data')
  excluded[name]=len(available)-len(required);result[name]=[available[key] for key in required]
 return result,excluded

def guard_new_holdout_rf(sets,manifest,span=4800):
 """Reserve unseen eval snippets, pruning overlapping RF from training.

 Aircraft bucket splits alone cannot prevent two aircraft sharing one RF burst.
 Touching half-open sample intervals are allowed; actual overlap is excluded.
 """
 import bisect
 from collections import defaultdict
 later={};intervals=defaultdict(list)
 for name in ('validation','test'):
  fixed=set(manifest['splits'][name]['sha256']);later[name]=[r for r in sets[name] if r[5] not in fixed]
  for row in later[name]:intervals[row[7]].append(row[8])
 for starts in intervals.values():starts.sort()
 kept=[];excluded=0
 for row in sets['train']:
  starts=intervals[row[7]];i=bisect.bisect_right(starts,row[8]-span)
  if i<len(starts) and starts[i]<row[8]+span:excluded+=1
  else:kept.append(row)
 return later,kept,excluded

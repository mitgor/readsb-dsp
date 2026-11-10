"""Verify compact masks preserve all measured RF frame instances and guards."""
from common import *
import bisect,collections
P=WORK/'prepared';cases=json.loads((P/'cases.json').read_text());report=[]
for name in sorted({c['reference_file'] for c in cases}):
 full=json.loads((P/name).read_text());small=json.loads((P/(Path(name).stem+'-compact.json')).read_text());cc=sorted([c for c in cases if c['reference_file']==name],key=lambda c:c['sample_start']);lo=[c['sample_start']*5+12000 for c in cc];hi=[(c['sample_start']+c['sample_count'])*5-12000 for c in cc]
 def inside(t):
  i=bisect.bisect_right(lo,t)-1;return i>=0 and t<hi[i]
 key=lambda r:(r['ticks'],r['message_hex']);checks={}
 for stream in ['stock','actual']:
  a=collections.Counter(key(r) for r in full[stream] if inside(r['ticks']));b=collections.Counter(key(r) for r in small[stream] if inside(r['ticks']));assert a==b;checks[stream+'_core_instances']=sum(a.values())
 addr=collections.defaultdict(list);tiny=collections.defaultdict(list)
 for r in full['stock']:addr[r['message_hex'][2:8]].append(r['ticks'])
 for r in small['stock']:tiny[r['message_hex'][2:8]].append(r['ticks'])
 for rows in [addr,tiny]:
  for v in rows.values():v.sort()
 points=[r for stream in ['stock','actual'] for r in full[stream] if inside(r['ticks'])]+small['annotations'];count=0
 def has(mapping,p,t):
  rows=mapping[p];i=bisect.bisect_left(rows,t-360000000);return i<len(rows) and rows[i]<=t
 for r in points:assert has(addr,r['message_hex'][2:8],r['ticks'])==has(tiny,r['message_hex'][2:8],r['ticks']);count+=1
 report.append({'file':name,**checks,'causal_address_queries_equal':count})
write(OUT/'compact-reference-parity.json',report);print(report)

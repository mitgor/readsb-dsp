"""Common-baseline attribution for recent quality-gated RF only; no decoding."""
from pathlib import Path
import json,bisect,collections,argparse
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--result',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();d=json.loads(a.result.read_text());P=a.root/'prepared';base=json.loads((P/'other-dsp-accepted.json').read_text());refs=json.loads((P/'references.json').read_text());positions=json.loads((P/'positions.json').read_text())['recent'];TOL=1440
maps=collections.defaultdict(list)
for r in positions:
 if r['quality']:maps[r['icao']].append(r)
def dist(r):
 v=[p for p in maps[r['message_hex'][2:8]] if p['available']<=r['unix'] and 0<=r['unix']-p['position_time']<=15]
 return max(v,key=lambda p:p['available'])['distance_nm'] if v else None
def band(n):
 if n is None:return 'unknown'
 for lo,hi in [(0,50),(50,100),(100,150),(150,180),(180,200),(200,250)]:
  if n<hi:return f'{lo}-{hi}'
 return '250+'
def match(r,rows):return any(q['message_hex']==r['message_hex'] and abs(q['ticks']-r['ticks'])<=TOL for q in rows)
def conflict(r,rows):return any(q['message_hex']!=r['message_hex'] and q['message_hex'][2:8]==r['message_hex'][2:8] and abs(q['ticks']-r['ticks'])<=48 for q in rows)
raw={k:[r for r in v if r['family']=='recent'] for k,v in d['guarded_rows'].items()};marginal={}
for name,rr in raw.items():marginal[name]=[r for r in rr if not match(r,base[r['refgroup']]) and not conflict(r,base[r['refgroup']])]
new=[]
for r in marginal['native']:
 rest=base[r['refgroup']]+[q for q in raw['executable'] if q['refgroup']==r['refgroup']]+refs[r['refgroup']]['actual']+refs[r['refgroup']]['annotations']
 if not match(r,rest) and not conflict(r,rest):new.append(r)
nonly=[r for r in marginal['native'] if not match(r,[q for q in marginal['executable'] if q['refgroup']==r['refgroup']])];eonly=[r for r in marginal['executable'] if not match(r,[q for q in marginal['native'] if q['refgroup']==r['refgroup']])];bins=collections.defaultdict(collections.Counter)
for name,rr in [('native_marginal',marginal['native']),('executable_marginal',marginal['executable']),('native_gained_if_replace',nonly),('executable_lost_if_replace',eonly),('native_additional_on_current',new)]:
 for r in rr:bins[band(dist(r))][name]+=1
out={'recent_only':True,'native_marginal_beyond_stock_and_other_dsp':len(marginal['native']),'executable_marginal_beyond_stock_and_other_dsp':len(marginal['executable']),'gained_if_replace':len(nonly),'lost_if_replace':len(eonly),'native_additional_on_current':len(new),'distance_bins':dict(bins),'new_native_rows':new,'scope':'Same recent RF and frozen current other-DSP replay, stock guards, actual unified and annotation masks. Short clips are a supplementary comparison, not representative of one-second live executable startup/trust behavior.'};a.output.write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='new_native_rows'},indent=2))

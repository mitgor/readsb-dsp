"""Post-measurement distance and full recorded-pipeline comparisons; no admission."""
import argparse,collections,json,math
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--result',type=Path,required=True);p.add_argument('--capture',type=Path,required=True);p.add_argument('--origin',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();private=json.loads(a.result.with_suffix('.private.json').read_text());data=json.loads((a.capture/'capture.private.json').read_text());origin=json.loads(a.origin.read_text());first=data['cases'][0]['first'];rfwall=data['cases'][0]['wall'];bins=['0–50','50–100','100–150','150–180','180–200','200–250','250+','unknown']
 def distance(r):
  when=rfwall+(r['ticks']-first*5)/12000000;icao=r['message_hex'][2:8]
  for snapshot in reversed(data['positions']):
   if snapshot['available']>when:continue
   found=[p for p in snapshot['aircraft'] if p['hex']==icao]
   if not found:continue
   pos=found[0];age=when-(snapshot['now']-pos['seen_pos'])
   if not 0<=age<=15 or pos.get('nic',0)<5 or pos.get('nac_p',0)<5 or pos.get('mlat') or pos.get('tisb'):return 'unknown'
   lat1,lon1,lat2,lon2=map(math.radians,[origin['lat'],origin['lon'],pos['lat'],pos['lon']]);h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2;nm=3440.065*2*math.asin(min(1,math.sqrt(h)))
   return bins[next((i for i,x in enumerate([50,100,150,180,200,250]) if nm<x),6)]
  return 'unknown'
 recorded=[r for b in data['base'] for r in b['extra']];others=[r for r in recorded if r['source']!='stream1090'];match=lambda r,ss:any(s['message_hex']==r['message_hex'] and abs(s['ticks']-r['ticks'])<=1440 for s in ss);out={}
 for result in private['results']:
  table={b:collections.Counter() for b in bins}
  for r in result['events']:
   bucket=table[distance(r)];bucket[r['source']]+=1;bucket['all']+=1;bucket['early' if r['lane']=='early' else 'fallback']+=1
   if not match(r,others):bucket['beyond_recorded_other_DSP']+=1
   if not match(r,recorded):bucket['beyond_recorded_full_pipeline']+=1
  out[result['mode']]={k:dict(v) for k,v in table.items()}
 summary=dict(distance_bins=out,range_source='Causal recorded stock positions only; NIC/NACp>=5, age<=15s, no MLAT/TIS-B. Unknown remains unknown; not independent ground truth or training labels.',recorded_full_producer_events=len(recorded),recorded_other_DSP_events=len(others),recorded_relay_frames=len(data['relay']),comparison_limit='Full recorded pipeline/relay masks have no per-method completion times. These are post-hoc coverage comparisons, not timed all-method replay.',distant_coverage_sufficient=False)
 a.output.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

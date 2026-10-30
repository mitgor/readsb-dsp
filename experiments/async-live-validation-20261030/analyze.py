"""Analyze observed transport, never create training labels or physical RF truth."""
import argparse,bisect,collections,hashlib,json,math,statistics
from pathlib import Path
from rescue.wire import BeastParser
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--private-cohort',type=Path);a=p.parse_args();D=a.input;O=a.output;O.mkdir(parents=True,exist_ok=True);r=json.loads((D/'result.json').read_text());lo=r['measurement_start'];hi=r['measurement_end']
for name,m in json.loads((D/'manifest.json').read_text()).items():
 f=D/name;assert f.stat().st_size==m['bytes'] and hashlib.sha256(f.read_bytes()).hexdigest()==m['sha256']
def lines(name):return [json.loads(v) for v in (D/name).read_text().splitlines()]
def stream(name):
 raw=(D/(name+'.beast')).read_bytes();parser=BeastParser();rows=[]
 for c in lines(name+'.chunks.jsonl'):rows.extend(dict(f,at=c['at']) for f in parser.feed(raw[c['offset']:c['offset']+c['bytes']]))
 return rows
stock=stream('stock');actual=stream('actual');batches=lines('batches.jsonl');offset=statistics.median(b['observed_unix']-b['observed_mono'] for b in batches)
class Index:
 def __init__(self,rows):
  self.d=collections.defaultdict(list)
  for row in rows:self.d[row['message_hex']].append(row['ticks'])
  for v in self.d.values():v.sort()
 def has(self,p,t,tol=1440):
  v=self.d.get(p,());i=bisect.bisect_left(v,t-tol);return i<len(v) and v[i]<=t+tol
stockindex=Index([dict(ticks=f['ticks_12mhz'],message_hex=f['message_hex']) for f in stock]);actualindex=Index([dict(ticks=f['ticks_12mhz'],message_hex=f['message_hex']) for f in actual])
actual_body=collections.Counter((f['message_hex'],f['ticks_12mhz'],f['signal_byte'],f['kind']) for f in actual)
stock_at=[s['at'] for s in stock];observed=[]
for b in batches:
 for e in b['batch'].get('extra',[]):
  t=(int(e['ticks'])+2398)%(1<<48);j=bisect.bisect_right(stock_at,b['observed_mono'])-1
  age=None if j<0 else (stock[j]['ticks_12mhz']-t)/12e6
  event_unix=None if j<0 else stock[j]['at']+offset-age
  observed.append(dict(source=e['source'],message_hex=e['message_hex'],ticks=t,observed_at=b['observed_mono'],created_unix=b['batch']['created_unix'],producer_observation_delay_s=b['observed_unix']-b['batch']['created_unix'],event_age_at_observation_s=age,event_unix=event_unix,stock_duplicate=stockindex.has(e['message_hex'],t),actual_relay_match=actualindex.has(e['message_hex'],t),measured=lo<=b['observed_mono']<hi))
cohort=[x for x in observed if x['measured']];observedindex=Index(observed)
def summary(v):
 v=sorted(x for x in v if x is not None and math.isfinite(x));return dict(n=len(v),min=v[0],median=statistics.median(v),p95=v[min(len(v)-1,int(.95*len(v)))],p99=v[min(len(v)-1,int(.99*len(v)))],max=v[-1]) if v else dict(n=0)
# Only literal prior stock snapshots with qualified position metadata supply range.
origin=json.loads((D/'receiver.private.json').read_text());lat,lon=origin.get('lat'),origin.get('lon');pos=collections.defaultdict(list)
for snap in lines('positions.jsonl'):
 for v in snap['aircraft']:
  if not all(type(v.get(k)) in (int,float) for k in ['lat','lon','seen_pos','nic','nac_p']):continue
  if v['nic']<5 or v['nac_p']<5 or v.get('mlat') or v.get('tisb'):continue
  if lat is None or lon is None:continue
  p1,p2=math.radians(lat),math.radians(v['lat']);dp=p2-p1;dl=math.radians(v['lon']-lon);distance=3440.065*2*math.asin(min(1,math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2)))
  pos[v['hex']].append(dict(available=snap['observed_unix'],position=snap['now']-v['seen_pos'],distance=distance))
def distance(row):
 t=row['event_unix'];v=[v for v in pos.get(row['message_hex'][2:8],[]) if t is not None and v['available']<=t-.005 and 0<=t-v['position']<=15]
 return max(v,key=lambda v:v['available'])['distance'] if v else None
def band(d):return 'unknown' if d is None else '0-50' if d<50 else '50-100' if d<100 else '100-150' if d<150 else '150-180' if d<180 else '180-200' if d<200 else '200-250' if d<250 else '250+'
for row in cohort:row['distance_nm']=distance(row)
profiles={};profile_times={};bins=collections.defaultdict(collections.Counter)
for name in ['strict250','compat3000']:
 events=[]
 for e in lines(name+'.emissions.jsonl'):
  f=BeastParser().feed(bytes.fromhex(e['wire_hex']))[0];events.append(dict(e,message_hex=f['message_hex'],signal_byte=f['signal_byte'],kind=f['kind']))
 idx=Index(events);selected=[x for x in cohort if idx.has(x['message_hex'],x['ticks'])];unique=[];seen=collections.defaultdict(list)
 for x in selected:
  t=x['ticks'];v=seen[x['message_hex']];j=bisect.bisect_left(v,t-1440)
  if j<len(v) and v[j]<=t+1440:continue
  bisect.insort(v,t);unique.append(x)
 for x in unique:
  if not x['stock_duplicate']:bins[band(x['distance_nm'])][name]+=1
 delays=[]
 for x in unique:
  matches=[e for e in events if e['message_hex']==x['message_hex'] and abs(e['ticks']-x['ticks'])<=1440]
  if matches:delays.append(min(e['at'] for e in matches)-x['observed_at'])
 profile_times[name]=events
 cohort_index=Index(cohort)
 exact_matches=sum(cohort_index.has(e['message_hex'],e['ticks'],0) and actual_body[(e['message_hex'],e['ticks'],e['signal_byte'],e['kind'])]>0 for e in events)
 profiles[name]=dict(exact_current_wire_matches=exact_matches,emissions_measured_cohort=len(unique),extras_beyond_final_observed_stock=sum(not x['stock_duplicate'] for x in unique),actual_relay_matched=sum(x['actual_relay_match'] for x in unique),lost_vs_actual=sum(x['actual_relay_match'] and not idx.has(x['message_hex'],x['ticks']) for x in cohort),new_vs_actual=sum(not x['actual_relay_match'] and not x['stock_duplicate'] for x in unique),queue_to_emit_s=summary(delays),by_method=dict(collections.Counter(x['source'] for x in unique if not x['stock_duplicate'])),stock_enqueue_s=summary(r['stock_enqueue_delay_s'][name]),whole_capture_core_cpu_s=r['relay_core_cpu_s'][name],whole_capture_core_percent=100*r['relay_core_cpu_s'][name]/r['wall_s'])
# This check is independent of method attribution: every real old-relay extra
# arriving in the measured interval must be witnessed in some captured outbox.
actual_extras=[f for f in actual if lo<=f['at']<hi and f['kind']==51 and not stockindex.has(f['message_hex'],f['ticks_12mhz'])]
unattributed=[f for f in actual_extras if not observedindex.has(f['message_hex'],f['ticks_12mhz'])]
# Actual stock relay delay via exact payload/timestamp/signal/type, multiplicity.
key=lambda f:(f['kind'],f['ticks_12mhz'],f['message_hex'],f['signal_byte']);arrivals=collections.defaultdict(collections.deque)
for f in actual:arrivals[key(f)].append(f['at'])
old_delay=[];stock_measure=[f for f in stock if lo<=f['at']<hi]
for f in stock_measure:
 if arrivals[key(f)]:old_delay.append(arrivals[key(f)].popleft()-f['at'])
actual_by_payload=collections.defaultdict(list)
for f in actual:actual_by_payload[f['message_hex']].append(f)
methods=[];begin=r['boundaries']['start']['metrics'];end=r['boundaries']['end']['metrics'];cpu_elapsed=end['elapsed_wall_s']-begin['elapsed_wall_s'];producer_counts=collections.Counter(x['source'] for x in cohort);actual_counts=collections.Counter(x['source'] for x in cohort if x['actual_relay_match'] and not x['stock_duplicate'])
for source,on in r['before']['methods'].items():
 cpu=end['methods'].get(source,{}).get('cpu_seconds',0)-begin['methods'].get(source,{}).get('cpu_seconds',0)
 rows=[x for x in cohort if x['source']==source];extra_latency={}
 for profile,events in profile_times.items():
  emission_delay=[];rf_age=[]
  for x in rows:
   matched=[e for e in events if e['message_hex']==x['message_hex'] and abs(e['ticks']-x['ticks'])<=1440]
   if matched:
    delta=min(e['at'] for e in matched)-x['observed_at'];emission_delay.append(delta)
    if x['event_age_at_observation_s'] is not None:rf_age.append(x['event_age_at_observation_s']+delta)
  extra_latency[profile]=dict(after_observation_s=summary(emission_delay),estimated_rf_age_s=summary(rf_age))
 old_latency=[];old_rf_age=[]
 for x in rows:
  matched=[f for f in actual_by_payload.get(x['message_hex'],()) if abs(f['ticks_12mhz']-x['ticks'])<=1440]
  if matched:
   delta=min(f['at'] for f in matched)-x['observed_at'];old_latency.append(delta)
   if x['event_age_at_observation_s'] is not None:old_rf_age.append(x['event_age_at_observation_s']+delta)
 methods.append(dict(latency=extra_latency,current_relay_after_observation_s=summary(old_latency),current_relay_estimated_rf_age_s=summary(old_rf_age),far180_actual=sum(x['distance_nm'] is not None and x['distance_nm']>=180 and x['actual_relay_match'] and not x['stock_duplicate'] for x in rows),far180_compat=sum(x['distance_nm'] is not None and x['distance_nm']>=180 and any(e['message_hex']==x['message_hex'] and abs(e['ticks']-x['ticks'])<=1440 for e in profile_times['compat3000']) for x in rows),method=source,enabled=on,producer_admitted=producer_counts[source],final_stock_duplicates=sum(x['stock_duplicate'] for x in rows),actual_relay_matched=actual_counts[source],strict250=profiles['strict250']['by_method'].get(source,0),compat3000=profiles['compat3000']['by_method'].get(source,0),existing_dsp_cpu_s=cpu,existing_one_core_percent=100*cpu/cpu_elapsed,observed_rf_age_s=summary(x['event_age_at_observation_s'] for x in rows),observation_delay_s=summary(x['producer_observation_delay_s'] for x in rows)))
coverage_complete=not any(r['count'].get(k,0) for k in ['inotify_overflow','outbox_deleted','inotify_file_gone','outbox_read_errors','observer_queue_overflow']) and not unattributed
result=dict(measured_seconds=hi-lo,full_capture_wall_s=r['wall_s'],source_coverage_complete=coverage_complete,observed_batches=r['count']['batches_read'],notifications=r['count']['inotify_json_events'],actual_wire_extras_in_measured_arrival_window=len(actual_extras),unattributed_actual_wire_extras=len(unattributed),stock_records_measured=len(stock_measure),actual_stock_records_missing=len(stock_measure)-len(old_delay),actual_stock_delay_s=summary(old_delay),profiles=profiles,methods=methods,distance_bins=dict(bins),observed_aircraft=len({x['message_hex'][2:8] for x in cohort}),estimated_distant_aircraft=len({x['message_hex'][2:8] for x in cohort if x['distance_nm'] is not None and x['distance_nm']>=180}),estimated_distant_opportunities=sum(x['distance_nm'] is not None and x['distance_nm']>=180 for x in cohort),metric_elapsed_s=cpu_elapsed,existing_total_worker_cpu_s=end['total_worker_cpu_seconds']-begin['total_worker_cpu_seconds'],existing_shared_cpu_s=end['shared_frontend_and_overhead_cpu_seconds']-begin['shared_frontend_and_overhead_cpu_seconds'],observer_cpu_s=r['observer_total_cpu_s'],observer_one_core_percent=100*r['observer_total_cpu_s']/r['wall_s'],stock_byte_hashes_equal=all(v==r['stock_sha256'] for v in r['stock_output_hashes'].values()),working_pipeline_unchanged=r['before']==r['after'],fr24_route=r['after']['fr24_host'],scope='Observed producer-admitted packet cohort at original publication times, method attribution not ablation; no extra DSP inference. No FR24/backend acceptance claim. Range is causal quality-screened stock context, not surveyed truth.')
(O/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
if a.private_cohort:a.private_cohort.write_text(json.dumps(cohort,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['source_coverage_complete','stock_records_measured','actual_stock_records_missing','estimated_distant_opportunities','distance_bins']},indent=2));print(json.dumps(methods,indent=2))

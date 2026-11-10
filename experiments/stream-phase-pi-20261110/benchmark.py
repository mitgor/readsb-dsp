"""Identical saved RF, unchanged native search and deployed full Stream1090.
All packet outputs are quarantined; never opens an SDR, mirror or feeder.
"""
from pathlib import Path
import argparse,json,ctypes,subprocess,time,resource,hashlib,bisect,collections,statistics,platform,os,math
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--repeat',type=int,default=1);a=p.parse_args();assert not a.output.exists();P=a.root/'prepared';cases=[c for c in json.loads((P/'cases.json').read_text()) if c['reference_coverage_complete']];refs=json.loads((P/'references.json').read_text());positions=json.loads((P/'positions.json').read_text());RATE=2400000;TOL=1440
class Event(ctypes.Structure):_fields_=[('ticks',ctypes.c_int64),('message',ctypes.c_uint8*14)]
lib=ctypes.CDLL(str(a.native.resolve()));lib.phase_scan.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int64,ctypes.c_int64,ctypes.POINTER(Event),ctypes.c_uint32];lib.phase_scan.restype=ctypes.c_uint32;lib.phase_event_size.restype=ctypes.c_uint32;assert lib.phase_event_size()==ctypes.sizeof(Event);buffer=(Event*16384)()
CRC=[]
for i in range(256):
 c=i<<16
 for _ in range(8):c=((c<<1)^ (0xfff409 if c&0x800000 else 0))&0xffffff
 CRC.append(c)
def valid(msg):
 try:
  raw=bytes.fromhex(msg)
  if len(raw)!=14 or raw[0]>>3!=17:return False
  crc=0
  for b in raw:crc=((crc<<8)&0xffffff)^CRC[((crc>>16)^b)&255]
  return crc==0
 except ValueError:return False
assert valid('8d40621d58c382d690c8ac2863a7') and not valid('8d40621d58c382d690c8ac2863a6')
def unique(rows):
 seen={};out=[]
 for t,msg in sorted(rows):
  if msg not in seen or t-seen[msg]>TOL:out.append((t,msg));seen[msg]=t
 return out
def decode(name,raw,c):
 start=time.process_time();child_before=resource.getrusage(resource.RUSAGE_CHILDREN);kernel=0
 if name=='native':
  mark=time.process_time();n=lib.phase_scan(ctypes.cast(ctypes.c_char_p(raw),ctypes.c_void_p),len(raw)//2,c['first_sample'],c['core_start'],buffer,len(buffer));kernel=time.process_time()-mark;assert n<=len(buffer),'Native output overflow';rows=[(int(buffer[i].ticks),bytes(buffer[i].message).hex()) for i in range(n)]
 else:
  mark=time.monotonic();r=subprocess.run([str(a.binary),'-s','2.4','-u','8'],input=raw,capture_output=True,timeout=30,check=True);rows=[]
  for line in r.stdout.splitlines():
   if not line.endswith(b';') or line[:1] not in (b'<',b'@'):continue
   try:t=int(line[1:13],16)+c['first_sample']*5;msg=(line[15:-1] if line[:1]==b'<' else line[13:-1]).decode().lower()
   except (ValueError,UnicodeDecodeError):continue
   if len(msg)==28:rows.append((t,msg))
 rows=unique([(t,msg) for t,msg in rows if valid(msg)]);after=resource.getrusage(resource.RUSAGE_CHILDREN);child=(after.ru_utime+after.ru_stime)-(child_before.ru_utime+child_before.ru_stime);parent=time.process_time()-start
 return rows,{'kernel_cpu_s':kernel,'child_cpu_s':child,'parent_cpu_s':parent,'decode_cpu_s':parent+child}
raw_events={'native':[],'executable':[]};cost=collections.defaultdict(collections.Counter);per_case=[]
with (P/'rf.bin').open('rb') as rf:
 for i,c in enumerate(cases):
  rf.seek(c['byte_offset']);raw=rf.read(c['bytes']);assert len(raw)==c['bytes'] and hashlib.sha256(raw).hexdigest()==c['sha256'];order=['native','executable'] if (i+a.repeat)%2 else ['executable','native'];row={'case':c['id'],'family':c['family'],'cost':{}}
  for name in order:
   events,timing=decode(name,raw,c);cost[c['family']+'_'+name].update(timing);row['cost'][name]=timing
   for t,msg in events:raw_events[name].append({'ticks':t,'message_hex':msg,'case':c['id'],'family':c['family'],'refgroup':c['refgroup']})
  per_case.append(row)
  if i%50==0:print('Completed cases',i+1,'/',len(cases),flush=True)
# Calibrate each implementation independently from SAME-window stock packets.
indices={}
for group,d in refs.items():
 by=collections.defaultdict(list)
 for r in d['stock']:
  if valid(r['message_hex']):by[r['message_hex']].append(r['ticks'])
 for v in by.values():v.sort()
 indices[group]=by
calibration={};samples={};group_offsets={}
for name,rows in raw_events.items():
 families=collections.defaultdict(list);groups=collections.defaultdict(list)
 for r in rows:
  v=indices[r['refgroup']].get(r['message_hex'],());j=bisect.bisect_left(v,r['ticks']);near=v[max(0,j-1):j+1]
  if near:
   t=min(near,key=lambda t:abs(t-r['ticks']))
   if abs(t-r['ticks'])<=60000:families[r['family']].append(t-r['ticks']);groups[r['refgroup']].append(t-r['ticks'])
 for family,delta in families.items():
  med=int(round(statistics.median(delta)));mad=statistics.median(abs(x-med) for x in delta);assert len(delta)>=100 and mad<=24,(name,family,len(delta),med,mad);calibration[family+'_'+name]={'anchors':len(delta),'offset_ticks':med,'mad_ticks':mad};samples[family,name]=med
 for group,delta in groups.items():
  family='long' if group=='long' else 'recent';med=statistics.median(delta);mad=statistics.median(abs(x-samples[family,name]) for x in delta);assert abs(med-samples[family,name])<=24 and mad<=24,(name,group,med,mad);group_offsets[name,group]={'anchors':len(delta),'median_ticks':med,'mad_from_family_ticks':mad}
for family in ['long','recent']:
 for name in ['native','executable']:assert (family,name) in samples
by_case={c['id']:c for c in cases};events={}
for name,rows in raw_events.items():
 out=[]
 for r in rows:
  c=by_case[r['case']];stock_tick=r['ticks']+samples[r['family'],name];rf_tick=stock_tick-samples[r['family'],'native']
  if c['core_start']*5<=rf_tick<c['core_end']*5:out.append(dict(r,ticks=stock_tick,unix=c['unix']+(rf_tick-c['first_sample']*5)/12000000))
 events[name]=out
# Shared causal stock/conflict/dedup guards. No prediction supplies an identity.
def index(rows):
 d=collections.defaultdict(list)
 for r in rows:d[r['message_hex']].append(r['ticks'])
 for v in d.values():v.sort()
 return d
def near(d,msg,t,tol=TOL):
 v=d.get(msg,());i=bisect.bisect_left(v,t-tol);return i<len(v) and v[i]<=t+tol
def address_index(rows):
 d=collections.defaultdict(list)
 for r in rows:d[r['message_hex'][2:8]].append((r['ticks'],r['message_hex']))
 return {k:(sorted(v),sorted(t for t,p in v)) for k,v in d.items()}
def conflict(d,msg,t):
 rows,times=d.get(msg[2:8],((),()));i=bisect.bisect_left(times,t-48);j=bisect.bisect_right(times,t+48);return any(p!=msg for s,p in rows[i:j])
def guarded(rows,ref):
 stock=ref['stock'];si=index(stock);identity=address_index(stock);own=address_index(rows);selected=collections.defaultdict(list);out=[];count=collections.Counter()
 for r in sorted(rows,key=lambda x:x['ticks']):
  msg=r['message_hex'];t=r['ticks'];count['raw_unique_candidates']+=1
  if near(si,msg,t):count['already_stock']+=1;continue
  rows_id,times=identity.get(msg[2:8],((),()));j=bisect.bisect_right(times,t)-1
  if j<0 or t-times[j]>360000000:count['no_causal_stock_identity']+=1;continue
  if conflict(identity,msg,t) or conflict(own,msg,t):count['conflict']+=1;continue
  if near(selected,msg,t):count['duplicate']+=1;continue
  selected[msg].append(t);out.append(r);count['guarded_beyond_stock']+=1
 return out,dict(count)
long_pos=sorted(positions['long'],key=lambda x:x['unix']);long_times=[p['unix'] for p in long_pos];long_maps=[{str(x[0]).lower():(x[1],x[2]) for x in p['aircraft']} for p in long_pos];rp=collections.defaultdict(list)
for p in positions['recent']:
 if p['quality']:rp[p['icao']].append(p)
for v in rp.values():v.sort(key=lambda p:p['available'])
def distance(r):
 addr=r['message_hex'][2:8];t=r['unix']
 if r['family']=='long':
  i=bisect.bisect_right(long_times,t)-1
  if i<0 or t-long_times[i]>10:return None
  v=long_maps[i].get(addr)
  if not v:return None
  nm,age=v
  if not isinstance(nm,(int,float)) or not isinstance(age,(int,float)) or not math.isfinite(nm) or not 0<=age+t-long_times[i]<=15:return None
  return nm
 v=[p for p in rp.get(addr,()) if p['available']<=t and 0<=t-p['position_time']<=15]
 return max(v,key=lambda p:p['available'])['distance_nm'] if v else None
def band(n):
 if n is None:return 'unknown'
 for lo,hi in [(0,50),(50,100),(100,150),(150,180),(180,200),(200,250)]:
  if n<hi:return f'{lo}-{hi}'
 return '250+'
def pair(left,right):
 by=collections.defaultdict(list)
 for i,r in enumerate(right):by[r['refgroup'],r['message_hex']].append((i,r['ticks']))
 used=set();both=[];only=[]
 for r in sorted(left,key=lambda r:r['ticks']):
  opts=[(abs(t-r['ticks']),i) for i,t in by[r['refgroup'],r['message_hex']] if i not in used and abs(t-r['ticks'])<=TOL]
  if opts:_,i=min(opts);used.add(i);both.append(r)
  else:only.append(r)
 return both,only,[r for i,r in enumerate(right) if i not in used]
guards={};accepted={};actual_extra={};families={}
for name,rr in events.items():
 result=[];on_top=[];counts={};mark=time.process_time()
 for group,ref in refs.items():
  rows=[r for r in rr if r['refgroup']==group]
  if not rows:continue
  markgroup=time.process_time();good,cnt=guarded(rows,ref);family=rows[0]['family'];cost[family+'_'+name]['guard_cpu_s']+=time.process_time()-markgroup;result+=good;counts[group]=cnt;ui=index(ref['actual']);conf=address_index(ref['actual']);ann=index(ref['annotations'])
  on_top += [r for r in good if not near(ui,r['message_hex'],r['ticks']) and not near(ann,r['message_hex'],r['ticks']) and not conflict(conf,r['message_hex'],r['ticks'])]
 guards[name]=counts;accepted[name]=result;actual_extra[name]=on_top
for family in ['long','recent']:
 cc=[c for c in cases if c['family']==family];core_samples=sum(c['core_end']-c['core_start'] for c in cc);seconds=core_samples/RATE;buckets={};sections={}
 for key,sets in [('raw',events),('guarded_beyond_stock',accepted),('beyond_recorded_actual',actual_extra)]:
  n=[r for r in sets['native'] if r['family']==family];e=[r for r in sets['executable'] if r['family']==family];both,nonly,eonly=pair(n,e);sections[key]={'native':len(n),'executable':len(e),'both':len(both),'native_only':len(nonly),'executable_only':len(eonly)};b=collections.defaultdict(collections.Counter)
  for label,rows in [('native',n),('executable',e),('both',both),('native_only',nonly),('executable_only',eonly)]:
   for r in rows:b[band(distance(r))][label]+=1
  buckets[key]=dict(b)
 cpu={}
 for name in ['native','executable']:
  v=cost[family+'_'+name];cpu[name]={**dict(v),'decode_cpu_s_per_rf_s':v['decode_cpu_s']/seconds,'decode_plus_guard_cpu_s_per_rf_s':(v['decode_cpu_s']+v['guard_cpu_s'])/seconds}
 families[family]={'cases':len(cc),'core_samples':core_samples,'core_seconds':seconds,'range_quality':cc[0]['range_quality'],'counts':sections,'distance_bins':buckets,'cpu':cpu}
digest=lambda rr:hashlib.sha256(json.dumps(sorted((r['case'],r['ticks'],r['message_hex']) for r in rr)).encode()).hexdigest()
result={'platform':platform.platform(),'repeat':a.repeat,'native_library_sha256':hashlib.sha256(a.native.read_bytes()).hexdigest(),'executable_sha256':hashlib.sha256(a.binary.read_bytes()).hexdigest(),'families':families,'calibration':calibration,'group_calibration':{str(k):v for k,v in group_offsets.items()},'digests':{f'{k}_{name}':digest(rows) for k,d in [('raw',events),('guarded',accepted),('actual_extra',actual_extra)] for name,rows in d.items()},'guard_counts':guards,'guarded_rows':accepted,'actual_extra_rows':actual_extra,'parent_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024 if platform.system()=='Darwin' else 1),'child_peak_rss_kib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/(1024 if platform.system()=='Darwin' else 1),'working_pipeline_changed':False,'scope':'C search kernel with common external causal stock guards versus full executable. Native readsb whole-module deadlines/admission costs are not benchmarked; long historical ranges are estimates, recent ranges quality-gated. No outputs forwarded or treated as labels.'}
a.output.write_text(json.dumps(result,indent=2));print(json.dumps({'families':families,'calibration':calibration,'peak_rss_kib':result['parent_peak_rss_kib']},indent=2))

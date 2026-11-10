"""Freeze uniform long windows and recent quality-qualified RF; no receiver access."""
from pathlib import Path
import json,struct,zlib,hashlib,os,bisect,collections,sys
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/stream-phase-pi-20261110';W=R/'data/transfer/stream-phase-pi-20261110';P=W/'prepared';sys.path.insert(0,str(R/'data/transfer/retrain-20261110/benchmark-runtime/src'))
from rescue.wire import BeastParser
protocol=json.loads((O/'protocol.json').read_text());source=Path(protocol['long_capture']);paired=Path(protocol['long_paired']);assert not source.is_symlink() and not paired.is_symlink();before=source.stat();RATE=2400000;HALO=600;TOTAL=RATE+2*HALO;WIRE=struct.Struct('!II');TAP=struct.Struct('<4sIIIQQQ');selected={round(5+i*(1189-5)/119) for i in range(120)};assert len(selected)==120;cases=[];reservations=[];seq=0;offset=0;checksum=hashlib.sha256();expected=epoch=first=anchor_sample=anchor_ns=None;buffer=bytearray();gaps=0;epochs=set();rf_trailing_bytes=0;paired_trailing_bytes=0
rawfile=P/'rf.bin';assert not rawfile.exists()
with rawfile.open('wb') as out,source.open('rb') as f:
 while header:=f.read(WIRE.size):
  checksum.update(header)
  if len(header)!=WIRE.size:rf_trailing_bytes=len(header);break
  length,check=WIRE.unpack(header);assert TAP.size<=length<=60040;packet=f.read(length);checksum.update(packet)
  if len(packet)!=length:rf_trailing_bytes=len(header)+len(packet);break
  assert zlib.crc32(packet)==check;magic,e,rate,n,sample,ns,dropped=TAP.unpack_from(packet);assert magic==b'RSC1' and rate==RATE and n==length-TAP.size and n%2==0;epochs.add(e);raw=packet[TAP.size:]
  if e!=epoch or sample!=expected:
   gaps+=epoch is not None;epoch=e;skip=-sample%3;first=sample+skip;anchor_sample=sample;anchor_ns=ns;buffer.clear();buffer.extend(raw[2*skip:])
  else:buffer.extend(raw)
  expected=sample+len(raw)//2
  while len(buffer)>=TOTAL*2:
   if seq in selected:
    blob=bytes(buffer[:2*TOTAL]);out.write(blob);cases.append({'id':f'long-{seq:04d}','family':'long','refgroup':'long','epoch':e,'first_sample':first,'sample_count':TOTAL,'core_start':first+HALO,'core_end':first+HALO+RATE,'unix':(anchor_ns+(first-anchor_sample)*1000000000//RATE)/1e9,'byte_offset':offset,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'range_quality':'estimated_stock_distance_no_NIC_NACp','rf_window_index':seq});offset+=len(blob);reservations.append({'epoch':int(e),'sample_start':int(first),'sample_count':TOTAL})
   del buffer[:RATE*2];first+=RATE;seq+=1
 assert seq==protocol['long_total_expected_windows'] and len(cases)==120
 # Recent corpus: preserve the verified one-ms core trim and exact sample clock.
 prior=R/'data/transfer/retrain-20261110/prepared';recent=[c for c in json.loads((prior/'cases.json').read_text()) if c['alignment']['verified'] and c['streams_complete']]
 for i,c in enumerate(recent):
  blob=(prior/c['file']).read_bytes();assert hashlib.sha256(blob).hexdigest()==c['sha256'];out.write(blob);cases.append({'id':f'recent-{i:04d}','family':'recent','refgroup':c['archive'],'epoch':c['epoch'],'first_sample':c['sample_start'],'sample_count':c['sample_count'],'core_start':c['sample_start']+2400,'core_end':c['sample_start']+c['sample_count']-2400,'unix':c['unix'],'byte_offset':offset,'bytes':len(blob),'sha256':c['sha256'],'range_quality':'causal_stock_NIC_NACp_5_age15','original_case':c['file']});offset+=len(blob);reservations.append({'epoch':int(c['epoch']),'sample_start':int(c['sample_start']),'sample_count':int(c['sample_count'])})
 out.flush();os.fsync(out.fileno())
after=source.stat();assert (before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
# Parse both complete historical taps; explicit large gaps reset partial records.
H=struct.Struct('>cQI');parsers={s:BeastParser() for s in [b'S',b'U']};last={};rows={s:[] for s in parsers};chunk_times={s:[] for s in parsers};snapshots=[];h=hashlib.sha256();stat=paired.stat()
with paired.open('rb') as f:
 while header:=f.read(H.size):
  h.update(header)
  if len(header)!=H.size:paired_trailing_bytes=len(header);break
  s,ns,n=H.unpack(header);assert n<=1000000;blob=f.read(n);h.update(blob)
  if len(blob)!=n:paired_trailing_bytes=len(header)+len(blob);break
  if s==b'J':
   d=json.loads(blob);snapshots.append({'unix':ns/1e9,'aircraft':d['aircraft']})
  elif s in parsers:
   t=ns/1e9;chunk_times[s].append(t)
   if s in last and t-last[s]>2:parsers[s]=BeastParser()
   last[s]=t
   for r in parsers[s].feed(blob):
    msg=r['message_hex']
    if len(msg)==28 and int(msg[:2],16)>>3==17:rows[s].append({'ticks':r['ticks_12mhz'],'message_hex':msg})
assert stat.st_size==paired.stat().st_size and stat.st_mtime_ns==paired.stat().st_mtime_ns
# Retain all selected core neighborhoods plus causal address-history witnesses.
cc=[c for c in cases if c['family']=='long'];starts=sorted(c['core_start']*5 for c in cc);ends={c['core_start']*5:c['core_end']*5 for c in cc}
def inside(t):
 i=bisect.bisect_right(starts,t+60000)-1;return i>=0 and t<=ends[starts[i]]+60000
stock=sorted(rows[b'S'],key=lambda r:r['ticks']);times=[r['ticks'] for r in stock];keep={(r['ticks'],r['message_hex']):r for r in stock if inside(r['ticks'])}
for c in cc:
 t=c['core_start']*5;lo=bisect.bisect_left(times,t-360000000-60000);hi=bisect.bisect_left(times,t-60000);seen=set()
 for r in reversed(stock[lo:hi]):
  addr=r['message_hex'][2:8]
  if addr not in seen:keep[r['ticks'],r['message_hex']]=r;seen.add(addr)
coverage={}
for c in cc:
 lo=c['unix']+(c['core_start']-c['first_sample'])/RATE;hi=lo+1;good=True
 for s in [b'S',b'U']:
  ts=chunk_times[s];i=bisect.bisect_right(ts,lo)-1;j=bisect.bisect_left(ts,hi);v=ts[max(0,i):min(len(ts),j+1)];good &= bool(i>=0 and j<len(ts) and v and max((b-a for a,b in zip(v,v[1:])),default=1e99)<=2)
 c['reference_coverage_complete']=bool(good)
references={'long':{'stock':sorted(keep.values(),key=lambda r:r['ticks']),'actual':[r for r in rows[b'U'] if inside(r['ticks'])],'annotations':[]}}
for c in cases:
 if c['family']!='recent':continue
 c['reference_coverage_complete']=True
 if c['refgroup'] not in references:
  base=Path(c['original_case']).name.rsplit('-',1)[0];file=prior/(base+'-references-compact.json');d=json.loads(file.read_text());references[c['refgroup']]={k:[dict(r,ticks=r['ticks']+2398) for r in d.get(k,[])] for k in ['stock','actual','annotations']}
positions={'recent':json.loads((prior/'positions.json').read_text()),'long':snapshots}
for n,d in [('cases.json',cases),('references.json',references),('positions.json',positions)]:
 with (P/n).open('w') as f:json.dump(d,f,separators=(',',':'));f.flush();os.fsync(f.fileno())
D=R/'data/raw/long-validation-stream-phase-pi-20261110';D.mkdir(exist_ok=False)
with (D/'reserved-intervals.json').open('w') as f:json.dump({'schema':'long-validation-v1','evaluation_only':True,'captures':reservations,'policy':'All benchmark RF evaluation-only, including previously consumed historical research capture. Not a prospective collection or supervised labels.','sources':[{'path':str(source),'sha256':checksum.hexdigest()},{'path':str(paired),'sha256':h.hexdigest()}]},f,indent=2);f.flush();os.fsync(f.fileno())
for d in [P,D]:fd=os.open(d,os.O_RDONLY);os.fsync(fd);os.close(fd)
report={'rf_incomplete_final_frame_excluded_bytes':rf_trailing_bytes,'paired_incomplete_final_chunk_excluded_bytes':paired_trailing_bytes,'long_source_bytes':source.stat().st_size,'long_source_sha256':checksum.hexdigest(),'paired_source_sha256':h.hexdigest(),'framed_complete_windows':seq,'discontinuities':gaps,'epochs':sorted(epochs),'selected_long':120,'covered_long':sum(c['reference_coverage_complete'] for c in cc),'recent':len(recent),'rf_bytes':offset,'reference_stock_original':len(stock),'reference_stock_retained':len(keep),'selection_fixed_before_decoding':True};(O/'preparation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

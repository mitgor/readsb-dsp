"""Strict same-transmission stock/no-fix RF labels, fixed exclusions and later RF holdout."""
from common import *
import base64,bisect,collections,gzip,subprocess,tarfile,time,os
import numpy as np
from scipy.signal import upfirdn
from rescue.ledger_verify import ledger_frames,verify_ledger
from rescue.merge import parse_readsb,df17
from rescue.research_reservations import load_reservations
from rescue.dsp import FIR,features,baseline,payloads
from rescue.telemetry import distance_nm
P=WORK/'prepared';P.mkdir(exist_ok=True);assert not (OUT/'labels.json').exists()
archives=sorted((RAW/'adsb-far-capture').glob('*.tar'));latest=archives[-1];reserved,rm=load_reservations(ROOT/'data/raw');counts=collections.Counter();cases=[];labels=[];positions=[];archive_reports=[]
# Lock all latest RF, including incomplete bursts, BEFORE labels/model fitting.
reserved_latest=[]
with tarfile.open(latest) as tar:
 for line in tar.extractfile('segments.jsonl'):
  r=json.loads(line)
  if r.get('record')=='continuous_segment':reserved_latest.append({k:int(r[k]) for k in ['epoch','sample_start','sample_count']})
reservation=ROOT/'data/raw/long-validation-retrain-companion-20261029/reserved-intervals.json'
write(reservation,dict(schema='long-validation-v1',evaluation_only=True,captures=reserved_latest,source_sha256=sha(latest),policy='Latest archive reserved before qualification/training; one final replay only after checkpoint freeze.'))
reserved,rm=load_reservations(ROOT/'data/raw')
# Audit CRC candidates without converting later repetitions into supervised labels.
crc=collections.Counter()
for f in sorted((RAW/'adsb-rescue/crc-verification').glob('*.jsonl.gz')):
 for line in gzip.open(f,'rt'):
  r=json.loads(line)
  if r.get('collector')!='broad-crc-verification-v1':continue
  raw=base64.b64decode(r['iq_uc8_base64'],validate=True);assert __import__('hashlib').sha256(raw).hexdigest()==r['iq_sha256'];crc['iq_verified']+=1
  same=any(x['message_hex']==r['target_hex'] and abs(x['ticks']-r['event_ticks'])<=48 for x in r.get('stock_prior',[])+r.get('stock_followup',[]));crc['same_transmission_stock_match']+=same
  crc['same_icao_only_or_later_repetition_quarantined']+=not same
  assert not r['training_eligible'];crc['quarantined']+=1
readsb=Path(os.environ.get('ADSB_LABEL_READSB','/Users/mit/Documents/Codex/2026-09-30/i-have-a-flightradar24-service-on/work/adsb-neural/readsb-reference/readsb'))
for archive in archives:
 with tarfile.open(archive) as tar:
  try:verification=verify_ledger(tar)
  except ValueError as error:verification={'archive_complete':False,'error':str(error),'policy':'Exclude open/incomplete bursts; separately verify closed continuous RF and stream coverage. No packet-snippet labels admitted.'}
  refs=ledger_frames(tar);begins={};ends={};groups=[]
  for line in tar.extractfile('ledger.jsonl'):
   r=json.loads(line)
   if r['record']=='rf_burst_begin':begins[r['burst_id']]=r
   if r['record']=='rf_burst_end':ends[r['burst_id']]=r
  for b in begins.values():
   air=b.get('receiver_context',{}).get('aircraft') or {};origin=b.get('origin')
   if not origin:continue
   for a in air.get('aircraft',[]):
    if not all(k in a for k in ['hex','lat','lon','seen_pos']):continue
    good=isinstance(a.get('nic'),(float,int)) and isinstance(a.get('nac_p'),(float,int)) and a['nic']>=5 and a['nac_p']>=5 and not any(k in a.get('mlat',[]) for k in ['lat','lon'])
    positions.append(dict(icao=a['hex'],available=air['now'],position_time=air['now']-a['seen_pos'],distance_nm=distance_nm(a['lat'],a['lon'],origin),quality=good))
  for line in tar.extractfile('segments.jsonl'):
   r=json.loads(line)
   if r.get('record')!='continuous_segment':continue
   if groups and groups[-1]['burst_id']==r['burst_id'] and groups[-1]['sample_start']+groups[-1]['sample_count']==r['sample_start'] and groups[-1]['byte_offset']+groups[-1]['sample_count']*2==r['byte_offset']:groups[-1]['sample_count']+=r['sample_count']
   else:groups.append(dict(r))
  stock=[dict(ticks=int(x['ticks_12mhz'])-2398,message_hex=x['message_hex']) for x in refs['stock'] if df17(x['message_hex'])];actual=[dict(ticks=int(x['ticks_12mhz'])-2398,message_hex=x['message_hex']) for x in refs['unified'] if df17(x['message_hex'])]
  by=collections.defaultdict(list)
  for r in stock:by[r['message_hex']].append(r['ticks'])
  for v in by.values():v.sort()
  reference_file=P/(archive.stem+'-references.json');write(reference_file,dict(stock=stock,actual=actual))
  continuous=tar.extractfile('continuous.uc8');ar=collections.Counter();combined=bytearray();mapping=[]
  for g in groups:
   b=begins[g['burst_id']];e=ends.get(g['burst_id'],{});trim=(-g['sample_start'])%3;count=g['sample_count']-trim
   if count<24000 or not e.get('streams_complete'):continue
   first=g['sample_start']+trim;pad=2400+(-(len(combined)//2))%3;combined.extend(bytes([127,128])*pad);at=len(combined)//2;continuous.seek(g['byte_offset']+trim*2);blob=continuous.read(count*2);assert len(blob)==count*2;combined.extend(blob);mapping.append((g['epoch'],g['sample_start'],at,count,first))
  combined.extend(bytes([127,128])*2400);teacher=P/(archive.stem+'-teacher.uc8');teacher.write_bytes(combined)
  cmd=[str(readsb),'--device-type','ifile','--ifile',str(teacher),'--iformat','UC8','--raw','--mlat','--no-fix','--no-fix-df'];run=subprocess.run(cmd,capture_output=True,text=True,timeout=90);assert run.returncode==0,run.stderr
  (P/(archive.stem+'-nofix.txt')).write_text(run.stdout);parsed=[r for r in parse_readsb(run.stdout) if df17(r['message_hex'])];cold_by=collections.defaultdict(list);all_deltas=[]
  for epoch,start,at,count,first in mapping:
   for r in parsed:
    sample=r['seconds']*2400000-at
    # Neutral separators cannot supply labels; trim both RF edges.
    if not 2400<=sample<count-2400:continue
    rr=dict(r,seconds=sample/2400000);cold_by[(epoch,start)].append(rr);tick=first*5+round(rr['seconds']*12e6);near=[t for t in by[rr['message_hex']] if abs(t-tick)<60000]
    if near:all_deltas.append(min(near,key=lambda t:abs(t-tick))-tick)
  archive_offset=int(np.median(all_deltas)) if all_deltas else 0;archive_mad=float(np.median(abs(np.array(all_deltas)-archive_offset))) if all_deltas else 1e9;archive_aligned=len(all_deltas)>=100 and abs(archive_offset)<=120 and archive_mad<=24
  for g in groups:
   bid=g['burst_id'];b=begins[bid];end=ends.get(bid,{});trim=(-g['sample_start'])%3;first=g['sample_start']+trim;count=g['sample_count']-trim
   if count<24000:ar['short_groups']+=1;continue
   if not end.get('streams_complete'):ar['incomplete_groups']+=1;continue
   assert g['epoch']==b['epoch']==end['epoch'] and first>=b['sample_start'] and first+count<=end['sample_end']
   assert g['byte_offset']+trim*2==b['rf_byte_start']+(first-b['sample_start'])*2
   ident=f'{archive.stem}-{len(cases):03d}';path=P/(ident+'.uc8');continuous.seek(g['byte_offset']+trim*2);raw=continuous.read(count*2);assert len(raw)==count*2;path.write_bytes(raw)
   unix=b['unix_start']+(first-b['sample_start'])/2400000
   case=dict(file=path.name,archive=archive.name,epoch=g['epoch'],sample_start=first,sample_count=count,unix=unix,holdout=archive==latest,rf_seconds=count/2400000,reference_file=reference_file.name,sha256=sha(path),streams_complete=True)
   # Independently decoded no-fix windows; separators/edges excluded above.
   cold=cold_by[(g['epoch'],g['sample_start'])];deltas=[]
   for r in cold:
    tick=first*5+round(r['seconds']*12e6);near=[t for t in by[r['message_hex']] if abs(t-tick)<60000]
    if near:deltas.append(min(near,key=lambda t:abs(t-tick))-tick)
   offset=int(np.median(deltas)) if deltas else 0;mad=float(np.median(abs(np.array(deltas)-offset))) if deltas else 1e9
   case['alignment']=dict(anchors=len(deltas),offset_ticks=offset,mad_ticks=mad,verified=archive_aligned and (not deltas or (mad<=24 and abs(offset-archive_offset)<=24)),archive_anchors=len(all_deltas),archive_offset=archive_offset,archive_mad=archive_mad)
   cases.append(case);ar['rf_groups']+=1
   if archive==latest or not case['alignment']['verified']:continue
   raw_np=(np.frombuffer(raw,np.uint8).reshape(-1,2).astype(np.float32)-127.5)/128;y=upfirdn(FIR,raw_np,up=5,down=3,axis=0)[17:];iq=(y[:,0]+1j*y[:,1]).astype(np.complex64)
   for r in cold:
    sample=round(r['seconds']*2400000);lo=first+sample-2400;hi=lo+4800;tick=first*5+round(r['seconds']*12e6)+offset
    if any(l<hi and h>lo for l,h in reserved[g['epoch']]):counts['reserved_overlap_rejected']+=1;continue
    if not any(abs(t-tick)<=24 for t in by[r['message_hex']]):counts['not_same_transmission_stock']+=1;continue
    pos=round(r['seconds']*4e6);positions4=np.arange(pos-4,pos+5)
    if positions4[0]<8 or positions4[-1]+488>=len(iq):continue
    chunks=iq[positions4[:,None]+np.arange(480)];power=abs(chunks[:,:32])**2;template=np.zeros(32,np.float32);template[[0,1,4,5,14,15,18,19]]=1;template-=.25;scores=(power@template)/np.sqrt(np.maximum((power**2).sum(1)*6,1e-12));j=int(np.argmax(scores));pos=int(positions4[j]);z=iq[pos-8:pos+488].copy();truth=np.frombuffer(bytes.fromhex(r['message_hex']),np.uint8).copy();errors=int(np.unpackbits(payloads(baseline(features(z[None,8:488])))[0]^truth).sum())
    if scores[j]<.4 or errors>24:counts['alignment_quality_rejected']+=1;continue
    t=unix+r['seconds'];addr=r['message_hex'][2:8];v=[v for v in positions if v['icao']==addr and v['available']<=t and 0<=t-v['position_time']<=15 and v['quality']];distance=max(v,key=lambda x:x['available'])['distance_nm'] if v else np.nan
    labels.append(dict(iq=z,truth=truth,icao=addr,distance=distance,epoch=g['epoch'],lo=lo,hi=hi,errors=errors,raw_sha=__import__('hashlib').sha256(raw[max(0,sample-2400)*2:(sample+2400)*2]).hexdigest(),case=ident));counts['qualified_stock_nofix']+=1;counts['qualified_far180']+=bool(np.isfinite(distance) and distance>=180)
   print(archive.name,ident,case['alignment'],len(labels),flush=True)
  archive_reports.append(dict(archive=archive.name,sha256=sha(archive),ledger=verification,counts=ar))
write(P/'cases.json',cases);write(P/'positions.json',positions)
# Attach new labels only to ICAO-compatible fixed splits, never replacing old holdouts.
oldroot=ROOT/'data/transfer/improvement-20261027/raw';manifest=json.loads((ROOT/'results/data-improvement-20261027/raw/dataset.json').read_text());sets={};seen_iq=set();seen_payload={};addr_split={};intervals=collections.defaultdict(list)
for k in ['test','validation','train']:
 loaded=np.load(oldroot/f'learning-{k}.npz');d={n:loaded[n] for n in loaded.files};sets[k]=[]
 for i in range(len(d['iq'])):
  z=d['iq'][i];truth=d['truth'][i];addr=str(d['icao'][i]);h=__import__('hashlib').sha256(z.tobytes()).hexdigest();epoch,lo,hi=manifest['splits'][k]['rf_intervals'][i]
  row=dict(iq=z,truth=truth,icao=addr,distance=float(d['distance'][i]),epoch=epoch,lo=lo,hi=hi,new=False,errors=0);sets[k].append(row);seen_iq.add(h);seen_payload[truth.tobytes()]=k;addr_split[addr]=k;intervals[epoch].append((lo,hi,k))
for r in sorted(labels,key=lambda r:(r['epoch'],r['lo'])):
 bucket=int(__import__('hashlib').sha256(r['icao'].encode()).hexdigest()[:8],16)%10;k=addr_split.get(r['icao'],'train' if bucket<7 else ('validation' if bucket<9 else 'test'));h=__import__('hashlib').sha256(r['iq'].tobytes()).hexdigest();payload=r['truth'].tobytes()
 if h in seen_iq or payload in seen_payload:counts['duplicate_iq_or_payload_rejected']+=1;continue
 if any(l<r['hi'] and hi>r['lo'] and split!=k for l,hi,split in intervals[r['epoch']]):counts['cross_split_rf_rejected']+=1;continue
 sets[k].append(dict(r,new=True));seen_iq.add(h);seen_payload[payload]=k;addr_split[r['icao']]=k;intervals[r['epoch']].append((r['lo'],r['hi'],k))
for k,rows in sets.items():np.savez_compressed(P/(k+'.npz'),iq=np.stack([r['iq'] for r in rows]),truth=np.stack([r['truth'] for r in rows]),icao=np.array([r['icao'] for r in rows]),distance=np.array([r['distance'] for r in rows]),new=np.array([r['new'] for r in rows]),errors=np.array([r['errors'] for r in rows]))
# Full cross-split assertions, including original prepared data.
audit={}
for k in sets:
 for q in sets:
  if k>=q:continue
  assert not set(r['icao'] for r in sets[k])&set(r['icao'] for r in sets[q]);assert not set(r['truth'].tobytes() for r in sets[k])&set(r['truth'].tobytes() for r in sets[q]);assert not set(__import__('hashlib').sha256(r['iq'].tobytes()).hexdigest() for r in sets[k])&set(__import__('hashlib').sha256(r['iq'].tobytes()).hexdigest() for r in sets[q]);audit[k+'_'+q]='ICAO/payload/IQ disjoint; new RF checked against all earlier opposite-split windows'
write(OUT/'labels.json',dict(counts=counts,crc_audit=crc,archives=archive_reports,splits={k:dict(windows=len(v),new=sum(r['new'] for r in v),far180=sum(np.isfinite(r['distance']) and r['distance']>=180 for r in v),new_far180=sum(r['new'] and np.isfinite(r['distance']) and r['distance']>=180 for r in v)) for k,v in sets.items()},cross_split=audit,reservation_manifests=rm,readsb_sha256=sha(readsb),policy='Same-transmission live stock plus independent no-fix DF17 replay, preamble-only alignment. New ranges require prior NIC/NACp>=5, no MLAT, age<=15s; not physical ground truth. Historical unverified distances are not used for new far weighting.'))
print(json.dumps(json.loads((OUT/'labels.json').read_text())['splits']),flush=True)

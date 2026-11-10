from pathlib import Path
import json,gzip,base64,hashlib,collections,os
import numpy as np
from scipy.signal import upfirdn
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/retrain-20261110';W=R/'data/transfer/retrain-20261110';P=W/'prepared';P.mkdir(exist_ok=True)
import sys
sys.path[:0]=[str(W/'runtime/src'),str(R/'reference')]
from rescue.dsp import FIR,features,baseline,payloads
ledger=json.loads((O/'learning-ledger.json').read_text());wanted={(r['epoch'],r['sample_start'],r['target_hex']):r for r in ledger['records'] if r.get('status') in ('qualified_split_eligible_pending_trigger','fixed_icao_test_evaluation_only')}
records={}
for day in ['20261030','20261031','20261101','20261104','20261107','20261109','20261110','20261110-manual-save']:
 for f in (R/f'results/daily-{day}').glob('*qualified.jsonl.gz'):
  for l in gzip.open(f,'rt'):
   x=json.loads(l);key=x['epoch'],x['sample_start'],x['target_hex']
   if key in wanted:records[key]=(x,str(f))
assert len(records)==len(wanted),(len(records),len(wanted))
sets={};seen=set();meta=[];counts=collections.Counter();sources=[]
for split in ['train','validation','test']:
 p=R/f'data/transfer/retrain-companion-20261029/prepared/{split}.npz';z=np.load(p);sets[split]={k:[v for v in z[k]] for k in z.files};sets[split]['new']=[False]*len(z['iq']);sources.append({'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()});seen.update(hashlib.sha256(x.tobytes()).hexdigest() for x in z['iq'])
for key,(x,file) in sorted(records.items()):
 raw=base64.b64decode(x['iq_uc8_base64']);assert hashlib.sha256(raw).hexdigest()==x['iq_sha256'];v=(np.frombuffer(raw,np.uint8).reshape(-1,2).astype(np.float32)-127.5)/128
 y=upfirdn(FIR,v,up=5,down=3,axis=0)[17:];iq=(y[:,0]+1j*y[:,1]).astype(np.complex64);center=round((x['event_ticks']-x['sample_start']*5)/3);positions=np.arange(center-4,center+5)
 if positions[0]<8 or positions[-1]+488>=len(iq):counts['rf_edge_rejected']+=1;continue
 chunks=iq[positions[:,None]+np.arange(480)];power=abs(chunks[:,:32])**2;template=np.zeros(32,np.float32);template[[0,1,4,5,14,15,18,19]]=1;template-=.25;scores=(power@template)/np.sqrt(np.maximum((power**2).sum(1)*6,1e-12));j=int(np.argmax(scores));at=int(positions[j]);z=iq[at-8:at+488].copy();truth=np.frombuffer(bytes.fromhex(x['target_hex']),np.uint8).copy();err=int(np.unpackbits(payloads(baseline(features(z[None,8:488])))[0]^truth).sum())
 if scores[j]<.4 or err>24:counts['preamble_alignment_rejected']+=1;continue
 h=hashlib.sha256(z.tobytes()).hexdigest()
 if h in seen:counts['transformed_iq_duplicate']+=1;continue
 seen.add(h);split=wanted[key]['proposed_split'];d=sets[split]
 for name,value in [('iq',z),('truth',truth),('icao',x['target_hex'][2:8]),('distance',x['distance_nm']),('new',True),('errors',err)]:d[name].append(value)
 meta.append({'split':split,'epoch':x['epoch'],'sample_start':x['sample_start'],'sample_count':x['sample_count'],'source_iq_sha256':x['iq_sha256'],'transformed_iq_sha256':h,'target_hex':x['target_hex'],'qualified_source':file,'preamble_shift_4msps':at-center,'distance_nm':x['distance_nm'],'event_unix':x['event_unix']});counts['prepared_'+split]+=1
for split,d in sets.items():np.savez_compressed(P/(split+'.npz'),**{k:np.stack(v) for k,v in d.items()})
for a,b in [('train','validation'),('train','test'),('validation','test')]:
 assert not set(sets[a]['icao'])&set(sets[b]['icao']);assert not set(map(bytes,sets[a]['truth']))&set(map(bytes,sets[b]['truth']));assert not {hashlib.sha256(z.tobytes()).hexdigest() for z in sets[a]['iq']}&{hashlib.sha256(z.tobytes()).hexdigest() for z in sets[b]['iq']}
train=[x for x in meta if x['split']=='train'];val=[x for x in meta if x['split']=='validation'];assert len(train)>=500 and len(val)>=100
report={'counts':dict(counts),'historical_sources':sources,'new_examples':meta,'learning_ledger_sha256':hashlib.sha256((O/'learning-ledger.json').read_bytes()).hexdigest(),'policy':'Original qualified stock UC8 with preamble-only timing search; fixed ICAO/payload/IQ/RF split ledger. Continuous RF reserved separately, never training. Historical replay retained. No receiver operations.'};(O/'prepared-data.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(counts)))

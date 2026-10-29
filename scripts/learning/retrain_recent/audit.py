"""Recheck actual prepared arrays, export/control gates and chronological holdout."""
from common import *
import itertools
import numpy as np
P=WORK/'prepared';ds={}
for k in ['train','validation','test']:
 f=np.load(P/(k+'.npz'));ds[k]={n:f[n] for n in f.files}
report=dict(splits={},cross_split={},models={})
for k,d in ds.items():
 report['splits'][k]=dict(windows=len(d['iq']),new=int(d['new'].sum()),new_far180=int((d['new']&np.isfinite(d['distance'])&(d['distance']>=180)).sum()),sha256=sha(P/(k+'.npz')))
for a,b in itertools.combinations(ds,2):
 x,y=ds[a],ds[b];v=dict(icao=len(set(x['icao'])&set(y['icao'])),payload=len(set(map(bytes,x['truth']))&set(map(bytes,y['truth']))),iq=len({__import__('hashlib').sha256(z.tobytes()).hexdigest() for z in x['iq']}&{__import__('hashlib').sha256(z.tobytes()).hexdigest() for z in y['iq']}));assert not any(v.values()),v;report['cross_split'][a+'_'+b]=v
for k in ['raw','dsp']:
 r=json.loads((OUT/k/'training.json').read_text());assert r['noise']['valid']==0 and r['export']['packet_bytes_exact'] and r['export']['bit_differences']==0;assert all(v['losses']==0 for v in r['metrics'].values());report['models'][k]=dict(noise=r['noise'],export=r['export'])
cases=json.loads((P/'cases.json').read_text());before=[c for c in cases if not c['holdout']];after=[c for c in cases if c['holdout']];assert max(c['unix']+c['rf_seconds'] for c in before)<min(c['unix'] for c in after)
trainaddrs=set(ds['train']['icao']);trainpayloads=set(bytes(p).hex() for p in ds['train']['truth']);refs=json.loads((P/after[0]['reference_file']).read_text());bounds=[(c['sample_start']*5,(c['sample_start']+c['sample_count'])*5) for c in after];observed=[r for r in refs['stock'] if any(lo<=r['ticks']<hi for lo,hi in bounds)];report['chronological_rf']=dict(rf_seconds=sum(c['rf_seconds'] for c in after),stock_packets=len(observed),stock_packets_with_training_icao=sum(r['message_hex'][2:8] in trainaddrs for r in observed),stock_packets_with_training_payload=sum(r['message_hex'] in trainpayloads for r in observed),policy='Temporally held-out RF, not claimed ICAO-disjoint. Windows train/validation/test are ICAO/payload/IQ-disjoint. Field packets matching a training payload cannot establish new-payload generalization. No post-freeze prospective RF was collected.')
write(OUT/'dataset-audit.json',report);print(json.dumps(report['chronological_rf']))

from common import *
import numpy as np,onnxruntime as ort,time,collections
from rescue.dsp import features,payloads
from rescue.model_cascade import CascadeSession,production_paths,valid_logits
opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1
paths=production_paths(ROOT);best=ROOT/'models/candidates/recent-20261029/dsp/tiny-rf-v1.onnx';old=ROOT/'models/candidates/daily-20261104/dsp/tiny-rf-v1.onnx';selected=json.loads((OUT/'selected.json').read_text());candidate=ROOT/selected['model'];raw=ROOT/'models/candidates/retrain-20261110/raw/tiny-rf-v1.onnx'
allpaths=paths+[best,old,candidate,raw];sessions=[ort.InferenceSession(str(p),opts,providers=['CPUExecutionProvider']) for p in allpaths]
sets={'current_original':sessions[:1],'current_production':sessions[:3],'current_plus_previous_best':sessions[:4],'previous_trial_companion':sessions[:4]+[sessions[4]],'new_raw_companion':sessions[:4]+[sessions[6]],'new_dsp_companion':sessions[:4]+[sessions[5]],'new_alone':[sessions[5]],'current_plus_new':sessions[:3]+[sessions[5]],'retain_previous_trial_plus_new':sessions[:5]+[sessions[5]]}
prepared=json.loads((OUT/'prepared-data.json').read_text());ledger=json.loads((OUT/'learning-ledger-pretraining.json').read_text());lookup={(r['epoch'],r['sample_start'],r['target_hex']):r for r in ledger['records']};meta={r['transformed_iq_sha256']:r for r in prepared['new_examples']};out={}
for split in ['validation','test']:
 d=np.load(WORK/'prepared'/(split+'.npz'));x=features(d['iq'][:,8:488]);truth=d['truth'];new=d['new'];far=new&np.isfinite(d['distance'])&(d['distance']>=180);fresh=np.zeros(len(x),bool)
 for i,z in enumerate(d['iq']):
  m=meta.get(__import__('hashlib').sha256(z.tobytes()).hexdigest())
  if m:
   r=lookup[m['epoch'],m['sample_start'],m['target_hex']];fresh[i]=not r.get('evaluated_candidate_run')
 results={};cost={}
 for name,ss in sets.items():
  mark=time.process_time();logits=CascadeSession(ss).run(None,{'iq_features':x})[0];cost[name]=time.process_time()-mark;p=payloads(logits);results[name]=(np.all(p==truth,1),valid_logits(logits),p)
 def delta(name,base):
  good,valid,p=results[name];before=results[base][0];return {'additions':int((good&~before).sum()),'losses':int((before&~good).sum()),'qualified_far_additions':int((good&~before&far).sum()),'qualified_far_losses':int((before&~good&far).sum()),'fresh_qualified_far_additions':int((good&~before&far&fresh).sum()),'fresh_qualified_far_losses':int((before&~good&far&fresh).sum())}
 out[split]={'windows':len(x),'new_qualified_far_windows':int(far.sum()),'fresh_qualified_far_windows':int((far&fresh).sum()),'methods':{k:{'exact_packets':int(v[0].sum()),'wrong_crc_valid':int((v[1]&~v[0]).sum()),'cpu_seconds':cost[k]} for k,v in results.items()},'new_vs_current_original':delta('new_alone','current_original'),'append_new_to_current':delta('current_plus_new','current_production'),'new_beyond_previous_best':delta('new_dsp_companion','current_plus_previous_best'),'new_vs_previous_trial':delta('new_dsp_companion','previous_trial_companion'),'append_after_previous_trial':delta('retain_previous_trial_plus_new','previous_trial_companion'),'scope':'Supplied packet-window reconstruction, not additional field receptions. Fresh excludes earlier candidate test evaluation; all checkpoints chosen on validation only.'}
write(OUT/'current-model-comparison.json',{'splits':out,'models':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in allpaths]});print(json.dumps(out,indent=2))

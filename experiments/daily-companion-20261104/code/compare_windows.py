from common import *
import numpy as np,onnxruntime as ort,time
from rescue.dsp import features,payloads
from rescue.model_cascade import CascadeSession,production_paths,valid_logits
opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1
paths=production_paths(ROOT);best=ROOT/'models/candidates/recent-20261029/dsp/tiny-rf-v1.onnx';candidate=ROOT/json.loads((OUT/'selected.json').read_text())['model'];sessions=[ort.InferenceSession(str(p),opts,providers=['CPUExecutionProvider']) for p in paths+[best,candidate]];out={}
for split in ['validation','test']:
 d=np.load(WORK/'prepared'/(split+'.npz'));x=features(d['iq'][:,8:488]);rows={};times={}
 for name,ss in [('frozen_original',sessions[:1]),('production_neural',sessions[:3]),('production_plus_previous_best',sessions[:4]),('production_plus_previous_best_plus_candidate',sessions)]:
  mark=time.process_time();logits=CascadeSession(ss).run(None,{'iq_features':x})[0];times[name]=time.process_time()-mark;p=payloads(logits);rows[name]=(p,np.all(p==d['truth'],axis=1),valid_logits(logits))
 base=rows['production_plus_previous_best'];new=rows['production_plus_previous_best_plus_candidate'];far=d['new']&np.isfinite(d['distance'])&(d['distance']>=180)
 out[split]={'windows':len(x),'new_distant_windows':int(far.sum()),'methods':{k:{'exact':int(v[1].sum()),'wrong_crc_valid':int((v[2]&~v[1]).sum()),'cpu_seconds':times[k]} for k,v in rows.items()},'incremental_over_previous_best':int((new[1]&~base[1]).sum()),'distant_incremental_over_previous_best':int((new[1]&~base[1]&far).sum()),'losses':int((base[1]&~new[1]).sum()),'scope':'Supplied packet windows only, NOT full pipeline field detections.'}
write(OUT/'window-comparison.json',out);print(json.dumps(out,indent=2))

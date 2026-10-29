"""Two fixed-seed additive companions; validation-only checkpoint choice."""
from common import *
import argparse,time
import numpy as np,torch,onnxruntime as ort
from rescue.model import TinyDecoder
from rescue.dsp import features,payloads,crc_batch
from rescue.model_cascade import CascadeSession,production_paths,valid_logits
from original_decoder import synth
p=argparse.ArgumentParser();p.add_argument('--variant',choices=['raw','dsp'],required=True);p.add_argument('--steps',type=int,default=1000);a=p.parse_args();dest=ROOT/f'models/candidates/recent-20261029/{a.variant}';dest.mkdir(parents=True,exist_ok=True);out=OUT/a.variant;out.mkdir(exist_ok=True);assert not (out/'training.json').exists()
torch.set_num_threads(2);torch.manual_seed(29102931);rng=np.random.default_rng(29102931);data={}
for k in ['train','validation','test']:
 loaded=np.load(WORK/'prepared'/(k+'.npz'));data[k]={n:loaded[n] for n in loaded.files}
assert data['train']['new'].sum()>0,'No qualified recent training labels; do not retrain unchanged data'
opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
paths=production_paths(ROOT);prior=CascadeSession([ort.InferenceSession(str(p),opts,providers=['CPUExecutionProvider']) for p in paths]);model=TinyDecoder();model.load_state_dict(torch.load(ROOT/'models/candidates/improvement-raw-20261027/tiny-rf-v1.pt',map_location='cpu',weights_only=True)['state_dict']);anchor=TinyDecoder();anchor.load_state_dict(model.state_dict());anchor.eval()
def infer(m,x):
 with torch.inference_mode():return np.concatenate([m(torch.from_numpy(x[i:i+128])).numpy() for i in range(0,len(x),128)])
val=data['validation'];vx=features(val['iq'][:,8:488]);vprior=prior.run(None,{'iq_features':vx})[0];vbase=payloads(vprior);vvalid=valid_logits(vprior);vtruth=val['truth'];vfar=val['new']&np.isfinite(val['distance'])&(val['distance']>=180)
def metric(logits,truth,base,base_valid,far,new):
 pred=payloads(logits);valid=valid_logits(logits);same=np.all(pred==truth,1);old=np.all(base==truth,1);take=~base_valid&valid;merged=base.copy();merged[take]=pred[take];good=np.all(merged==truth,1)
 return dict(windows=len(pred),candidate_exact=int(same.sum()),candidate_wrong_crc=int((valid&~same).sum()),baseline_exact=int(old.sum()),combined_exact=int(good.sum()),additions=int((good&~old).sum()),losses=int((old&~good).sum()),new_windows=int(new.sum()),new_additions=int((good&~old&new).sum()),qualified_far180_windows=int(far.sum()),qualified_far180_additions=int((good&~old&far).sum()),bit_errors=int(np.unpackbits(pred^truth,axis=1).sum()))
train=data['train'];tx=features(train['iq'][:,8:488]);trprior=prior.run(None,{'iq_features':tx})[0];hard=~np.all(payloads(trprior)==train['truth'],1);far=train['new']&np.isfinite(train['distance'])&(train['distance']>=180);prob=(1+2*hard+3*far+train['new']).astype(float);prob/=prob.sum();opt=torch.optim.AdamW(model.parameters(),lr=.0003,weight_decay=.01);best=None;history=[];begin=time.monotonic()
for step in range(a.steps):
 ids=rng.choice(len(train['iq']),64,p=prob);z=train['iq'][ids].copy();truth=train['truth'][ids];rms=np.sqrt(np.mean(abs(z[:,8:488])**2,axis=1,keepdims=True));noise=(rng.normal(size=z.shape)+1j*rng.normal(size=z.shape))*rng.uniform(.025,.25,(64,1))*rms/np.sqrt(2);z+=noise.astype(np.complex64)*(rng.random((64,1))<.65)
 if a.variant=='dsp':
  from rescue.dsp_training import views
  real,_=views(z,rng)
 else:real=z[np.arange(64)[:,None],8+rng.integers(-1,2,(64,1))+np.arange(480)]
 fake,ft,_,_=synth(rng,64,snr=(3,20),overlap=True);x=features(np.concatenate([real,fake]));truth=np.concatenate([truth,ft]);target=torch.from_numpy(np.unpackbits(truth,axis=1).astype(np.float32));model.train();logits=model(torch.from_numpy(x));loss=torch.nn.functional.binary_cross_entropy_with_logits(logits,target)
 with torch.no_grad():anch=anchor(torch.from_numpy(x));known=((anch>0)==target.bool()).all(1).float()
 loss+=.02*(((logits.clamp(-20,20)-anch.clamp(-20,20))**2).mean(1)*known).mean();opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);opt.step()
 if (step+1)%100==0:
  model.eval();v=metric(infer(model,vx),vtruth,vbase,vvalid,vfar,val['new']);key=(-v['candidate_wrong_crc'],v['qualified_far180_additions'],v['additions'],-v['bit_errors']);history.append(dict(step=step+1,validation=v,loss=float(loss.detach()),wall_s=time.monotonic()-begin));print(json.dumps(history[-1]),flush=True)
  if best is None or key>best:best=key;chosen={k:v.detach().clone() for k,v in model.state_dict().items()};chosen_step=step+1
model.load_state_dict(chosen);model.eval();torch.save(dict(state_dict=chosen,steps=chosen_step,seed=29102931,training='Qualified recent no-fix/live-stock labels plus unchanged historical RF and synthetic replay; additive only'),dest/'tiny-rf-v1.pt')
report=dict(variant=a.variant,steps=a.steps,selected_step=chosen_step,history=history,wall_s=time.monotonic()-begin,selection='Validation only, wrong-CRC first, qualified new far additions, total additions, bit errors. Never select using test/RF holdout.',model_references={str(p):sha(p) for p in paths},metrics={})
for k,d in data.items():
 x=features(d['iq'][:,8:488]);b=prior.run(None,{'iq_features':x})[0];report['metrics'][k]=metric(infer(model,x),d['truth'],payloads(b),valid_logits(b),d['new']&np.isfinite(d['distance'])&(d['distance']>=180),d['new'])
fake,ft,_,_=synth(np.random.default_rng(29102999),4096,snr=(3,20),overlap=True);pred=payloads(infer(model,features(fake)));valid=(crc_batch(pred)==0)&(pred[:,0]>>3==17);report['synthetic']=dict(windows=4096,exact=int(np.all(pred==ft,1).sum()),other_crc_valid=int((valid&~np.all(pred==ft,1)).sum()),limitation='A secondary real synthetic interferer is not necessarily a false decode; non-target valid outputs remain quarantined.')
noise=(rng.normal(size=(20000,480))+1j*rng.normal(size=(20000,480))).astype(np.complex64);report['noise']=dict(windows=20000,valid=int(valid_logits(infer(model,features(noise))).sum()))
onnx=dest/'tiny-rf-v1.onnx';example=torch.from_numpy(features(fake[:1]));torch.onnx.export(model,example,str(onnx),input_names=['iq_features'],output_names=['bit_logits'],dynamic_axes={'iq_features':{0:'batch'},'bit_logits':{0:'batch'}},opset_version=17,dynamo=False);session=ort.InferenceSession(str(onnx),opts,providers=['CPUExecutionProvider']);x=np.concatenate([features(fake[:512]),vx]);expected=infer(model,x);actual=session.run(None,{'iq_features':x})[0];report['export']=dict(sha256=sha(onnx),max_logit_difference=float(abs(expected-actual).max()),bit_differences=int(((expected>0)!=(actual>0)).sum()),packet_bytes_exact=payloads(expected).tobytes()==payloads(actual).tobytes());report['eligible_for_rf_evaluation']=report['noise']['valid']==0 and report['export']['packet_bytes_exact'] and report['metrics']['validation']['candidate_wrong_crc']==0
write(out/'training.json',report);print(json.dumps(report['metrics']),flush=True)

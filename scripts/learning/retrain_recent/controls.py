"""Independent fixed-seed controls; retain secondary labels for collision audit."""
from common import *
import numpy as np,onnxruntime as ort
from rescue.dsp import features,payloads
from rescue.model_cascade import valid_logits
import original_decoder as synthmod
opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1
sessions={k:ort.InferenceSession(str(ROOT/f'models/candidates/recent-20261029/{k}/tiny-rf-v1.onnx'),opts,providers=['CPUExecutionProvider']) for k in ['raw','dsp']}
def infer(session,z):
 return np.concatenate([session.run(None,{'iq_features':features(z[i:i+128])})[0] for i in range(0,len(z),128)])
original=synthmod.packets;captured=[]
def capture(rng,n):
 result=original(rng,n);captured.append(result.copy());return result
synthmod.packets=capture;z,truth,collision,snr=synthmod.synth(np.random.default_rng(29102999),4096,snr=(3,20),overlap=True);secondary=captured[1];synthmod.packets=original;report={'overlap':{}}
for k,session in sessions.items():
 logits=infer(session,z);pred=payloads(logits);valid=valid_logits(logits);primary=np.all(pred==truth,1);other=np.all(pred==secondary,1);report['overlap'][k]=dict(windows=len(z),primary=int(primary.sum()),secondary_valid=int((valid&~primary&other).sum()),unaccounted_valid=int((valid&~primary&~other).sum()))
clean,truth,_,_=synthmod.synth(np.random.default_rng(29103011),4096,snr=(3,20),overlap=False);noise=(np.random.default_rng(29103013).normal(size=(20000,480))+1j*np.random.default_rng(29103017).normal(size=(20000,480))).astype(np.complex64);report['clean']={};report['noise']={}
for k,session in sessions.items():
 logits=infer(session,clean);pred=payloads(logits);same=np.all(pred==truth,1);report['clean'][k]=dict(windows=len(clean),exact=int(same.sum()),wrong_crc_valid=int((valid_logits(logits)&~same).sum()));report['noise'][k]=dict(windows=len(noise),valid=int(valid_logits(infer(session,noise)).sum()))
write(OUT/'controls.json',report);print(json.dumps(report,indent=2))

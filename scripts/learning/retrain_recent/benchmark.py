"""Frozen add-only RF benchmark against all enabled DSP, old neural and Stream1090.
No networking/receiver I/O; all candidate packets remain quarantined.
"""
from common import *
import argparse,bisect,collections,os,platform,resource,subprocess,time
import numpy as np,onnxruntime as ort
from rescue.runtime import RescueDecoder
from rescue.pipeline_v3 import enable_v3
from rescue.model_cascade import CascadeSession,production_paths,valid_logits
from rescue.workers import CoherentWorker,merge_events
from rescue.shadow import evaluate
from rescue.stream1090_shadow import parse_avr
from rescue.pulse_comparison import compare,index,nearby
from rescue.telemetry import distance_bin
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
selected=json.loads((OUT/'selected.json').read_text());candidate=ROOT/selected['model'];assert sha(candidate)==selected['sha256'];P=WORK/'prepared';allcases=json.loads((P/'cases.json').read_text());cases=[c for c in allcases if c['holdout'] and c['alignment']['verified']];assert cases
live=json.loads((OUT/'live-baseline.json').read_text());methods=live['method_switches'];assert {k for k,v in methods.items() if v}=={'energy','crc','timing','soft','matched','coherent','neural','stream1090'}
opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
paths=production_paths(ROOT);sessions=[ort.InferenceSession(str(p),opts,providers=['CPUExecutionProvider']) for p in paths];new=ort.InferenceSession(str(candidate),opts,providers=['CPUExecutionProvider'])
class AddSession:
 def __init__(self):self.old=CascadeSession(sessions);self.cpu=0.;self.windows=0;self.valid=0
 def run(self,n,inputs):
  result=self.old.run(n,inputs)[0];ids=np.flatnonzero(~valid_logits(result))
  if len(ids):
   mark=time.process_time();logits=new.run(n,{'iq_features':np.ascontiguousarray(inputs['iq_features'][ids])})[0];good=valid_logits(logits);result[ids[good]]=logits[good];self.cpu+=time.process_time()-mark;self.windows+=len(ids);self.valid+=int(good.sum())
  return [result]
def decoder(session):
 d=RescueDecoder(paths[0],frontend='native',broad_crc=True,neural=True,methods=('timing','soft','matched'));enable_v3(d);d.session=session;return d
base=decoder(CascadeSession(sessions));added_session=AddSession();combined=decoder(added_session)
cfg=live['workers']['config'];coherent=CoherentWorker(cfg['coherent_threshold'],cfg['coherent_budget'],True,False,str(ROOT/'models/pulse-sequence.json'),True,True,True);coherent.decoder.coherent_enabled=True;coherent.decoder.sequence_enabled=False;coherent.decoder.acquisition_enabled=False
stream=Path(os.environ.get('STREAM1090_BINARY',str(WORK/'stream1090/build/stream1090')))
refs=json.loads((P/cases[0]['reference_file']).read_text());stock=refs['stock'];actual=refs['actual'];positions=json.loads((P/'positions.json').read_text());rows_base=[];rows_extended=[];stream_raw=[];records=[];cost=collections.Counter();by=collections.defaultdict(list)
for r in stock:by[r['message_hex']].append(r['ticks'])
for v in by.values():v.sort()
for c in cases:
 path=P/c['file'];assert sha(path)==c['sha256'];mark=time.process_time();baseline,detail=base.decode(path,raw_events=True);dspcpu=time.process_time()-mark;mark=time.process_time();extended,detail2=combined.decode(path,raw_events=True);extcpu=time.process_time()-mark;mark=time.process_time();coh,cd=coherent.decode(path,raw_events=True);cohcpu=time.process_time()-mark
 before=resource.getrusage(resource.RUSAGE_CHILDREN);run=subprocess.run([str(stream),'-s','2.4','-u','8'],input=path.read_bytes(),capture_output=True,timeout=30);assert run.returncode==0;after=resource.getrusage(resource.RUSAGE_CHILDREN);streamcpu=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
 start=c['sample_start']*5+12000;end=(c['sample_start']+c['sample_count'])*5-12000
 def event(r):
  tick=c['sample_start']*5+round(r['sample_4msps']*3);return dict(r,ticks=tick,unix=c['unix']+(tick-c['sample_start']*5)/12e6,case=c['file'])
 for rr,source in [(baseline+coh,rows_base),(extended,rows_extended)]:
  for r in rr:
   if r['source']=='broad_crc':continue
   row=event(r)
   if start<=row['ticks']<end:source.append(row)
 for tick,message in parse_avr(run.stdout,c['sample_start']):stream_raw.append(dict(ticks=tick,message_hex=message,source='stream1090',case=c['file']))
 costs=dict(dsp=dspcpu,coherent=cohcpu,stream1090=streamcpu,extended_dsp=extcpu);cost.update(costs);records.append(dict(file=c['file'],rf_seconds=c['rf_seconds'],cpu_seconds=costs,raw_baseline=len(baseline),raw_coherent=len(coh)));print(c['file'],costs,flush=True)
# Calibrate Stream1090 across short disjoint bursts using identical stock payloads.
# Packet edges and RF gaps never become candidate windows.
deltas=[]
for r in stream_raw:
 v=by[r['message_hex']];i=bisect.bisect_left(v,r['ticks']);close=v[max(0,i-1):i+1]
 if close and abs((t:=min(close,key=lambda t:abs(t-r['ticks'])))-r['ticks'])<=60000:deltas.append(t-r['ticks'])
offset=int(np.median(deltas)) if deltas else 0;mad=float(np.median(abs(np.array(deltas)-offset))) if deltas else 1e9;assert len(deltas)>=100 and mad<=360,'Current Stream1090 comparison not clock aligned'
case_map={c['file']:c for c in cases};stream_events=[]
for r in stream_raw:
 c=case_map[r['case']];tick=r['ticks']+offset
 if c['sample_start']*5+12000<=tick<(c['sample_start']+c['sample_count'])*5-12000:stream_events.append(dict(r,ticks=tick,unix=c['unix']+(tick-c['sample_start']*5)/12e6))
rows_base+=stream_events
# Keep original live pipeline output first; never replace its valid packets.
accepted,alignment,guards=evaluate(stock,rows_base,0,2**63);assert alignment['verified'],alignment
extra,decisions=compare(rows_extended,stock,actual,rows_base+accepted)
kept=[]
for r in extra:
 if any(q['message_hex']!=r['message_hex'] and q['message_hex'][2:8]==r['message_hex'][2:8] and abs(q['ticks']-r['ticks'])<=48 for q in rows_base+actual):decisions['baseline_conflict']=decisions.get('baseline_conflict',0)+1
 else:kept.append(r)
# Verify that extension did not lose any baseline DSP/neural outputs before union.
extindex=index(rows_extended);missing_raw=[r for r in rows_base if r['source'] not in ['coherent','stream1090'] and not nearby(extindex,r['message_hex'],r['ticks'])]
def dist(r):
 values=[v for v in positions if v['icao']==r['message_hex'][2:8] and v['quality'] and v['available']<=r['unix'] and 0<=r['unix']-v['position_time']<=15];return max(values,key=lambda v:v['available'])['distance_nm'] if values else None
bins=collections.defaultdict(collections.Counter)
for kind,rows in [('current_guarded_dsp_extras',accepted),('candidate_additions',kept)]:
 for r in rows:r['distance_nm']=dist(r);bins[distance_bin(r['distance_nm'])][kind]+=1
seconds=sum(c['rf_seconds'] for c in cases);basecpu=cost['dsp']+cost['coherent']+cost['stream1090'];digest=lambda rr:__import__('hashlib').sha256(json.dumps(sorted((r['ticks'],r['message_hex']) for r in rr)).encode()).hexdigest()
result=dict(hardware=platform.platform(),candidate_sha256=sha(candidate),cases=records,rf_seconds=seconds,effective_rf_seconds=sum(max(0,c['rf_seconds']-.002) for c in cases),baseline_methods=methods,baseline_models=[sha(p) for p in paths],alignment=alignment,stream_alignment=dict(anchors=len(deltas),offset=offset,mad=mad),guards=guards,candidate_guards=decisions,baseline_guarded_extras=len(accepted),raw_extension_losses=len(missing_raw),raw_extension_loss_events=missing_raw,add_only_baseline_losses=0,unique_additions_beyond_complete_pipeline=len(kept),distance_bins=dict(bins),extras=kept,baseline_digest=digest(accepted),extra_digest=digest(kept),cpu_seconds=cost,baseline_cpu_seconds_per_rf_second=basecpu/seconds,incremental_inference_cpu_seconds_per_rf_second=added_session.cpu/seconds,incremental_inference_percent_of_baseline=100*added_session.cpu/basecpu,candidate_windows=added_session.windows,candidate_valid_window_outputs=added_session.valid,scope='Chronological RF held out before fitting; captured before candidate freeze, not post-freeze prospective RF. Full enabled replay union incl Stream1090 plus recorded stock/unified masks. Broad CRC computation included, quarantined CRC output excluded. All candidate outputs quarantined. Serial algorithm CPU excludes live transport and is not electrical power.',working_setup_changed=False)
write(a.output,result);print(json.dumps({k:result[k] for k in ['rf_seconds','baseline_guarded_extras','unique_additions_beyond_complete_pipeline','distance_bins','raw_extension_losses','baseline_cpu_seconds_per_rf_second','incremental_inference_percent_of_baseline']}),flush=True)

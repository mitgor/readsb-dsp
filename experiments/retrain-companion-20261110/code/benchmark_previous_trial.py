"""Frozen offline full-pipeline plus companion replay; never connects to a feeder."""
from common import *
import argparse,bisect,collections,platform,resource,subprocess,time
import numpy as np,onnxruntime as ort
from rescue.runtime import RescueDecoder
from rescue.pipeline_v3 import enable_v3
from rescue.fir_cached import FirBackend
from rescue.coherent_extended_opt import ExtendedNeonBackend
from rescue.model_cascade import CascadeSession,production_paths,valid_logits
from rescue.workers import CoherentWorker
from rescue.shadow import evaluate
from rescue.stream1090_shadow import parse_avr
from rescue.pulse_comparison import compare,index,nearby
from rescue.telemetry import distance_bin
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
selected=json.loads((OUT/'previous-trial-selection.json').read_text());candidate=ROOT/selected['model'];assert sha(candidate)==selected['sha256']
P=WORK/'prepared';cases=[c for c in json.loads((P/'cases.json').read_text()) if c['alignment']['verified'] and c['streams_complete']];assert cases
live=json.loads((OUT/'live-baseline.json').read_text());methods=live['method_switches'];assert {k for k,v in methods.items() if v}=={'energy','crc','timing','soft','matched','coherent','neural','stream1090'}
opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1;opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
paths=production_paths(ROOT);best=ROOT/'models/candidates/recent-20261029/dsp/tiny-rf-v1.onnx';sessions=[ort.InferenceSession(str(p),opts,providers=['CPUExecutionProvider']) for p in paths+[best]];new=ort.InferenceSession(str(candidate),opts,providers=['CPUExecutionProvider'])
class Session:
 def __init__(self,ss,append=False):self.old=CascadeSession(ss);self.cpu=0.;self.windows=0;self.valid=0;self.append=append
 def run(self,n,inputs):
  result=self.old.run(n,inputs)[0]
  if self.append:
   ids=np.flatnonzero(~valid_logits(result))
   if len(ids):
    mark=time.process_time();logits=new.run(n,{'iq_features':np.ascontiguousarray(inputs['iq_features'][ids])})[0];good=valid_logits(logits);result[ids[good]]=logits[good];self.cpu+=time.process_time()-mark;self.windows+=len(ids);self.valid+=int(good.sum())
  return [result]
def decoder(session):
 d=RescueDecoder(paths[0],frontend='native',broad_crc=True,neural=True,methods=('timing','soft','matched'));enable_v3(d);b=FirBackend();d.blocks=b.iq_blocks;d.scores=b.candidate_scores;d.dsp_candidates=b.dsp_candidates;d.soft_decode=b.soft_decode;d.optimized_backend=b;d.session=session;return d
added=Session(sessions,True);added_current=Session(sessions[:3],True);production=decoder(Session(sessions[:3]));previous=decoder(Session(sessions));combined=decoder(added);combined_current=decoder(added_current)
cfg=live['workers']['config'];coherent=CoherentWorker(cfg['coherent_threshold'],cfg['coherent_budget'],True,False,str(ROOT/'models/pulse-sequence.json'),True,True,True)
class FirExtended(FirBackend,ExtendedNeonBackend):pass
b=FirExtended();coherent.backend=b;coherent.decoder.backend=b;coherent.decoder.score_function=b.coherent_scores;coherent.decoder.coherent_enabled=True;coherent.decoder.sequence_enabled=False;coherent.decoder.acquisition_enabled=False
stream=Path(os.environ.get('STREAM1090_BINARY',str(ROOT/'data/transfer/retrain-companion-20261029/stream1090/build/stream1090')))
refs=[json.loads((P/(Path(f).stem+'-compact.json')).read_text()) for f in sorted({c['reference_file'] for c in cases})];stock=[r for f in refs for r in f['stock']];actual=[r for f in refs for r in f['actual']];annotations=[r for f in refs for r in f.get('annotations',[])];positions=json.loads((P/'positions.json').read_text());rows_prod=[];rows_prev=[];rows_candidate=[];rows_current=[];stream_raw=[];records=[];cost=collections.Counter();by=collections.defaultdict(list)
for r in stock:by[r['message_hex']].append(r['ticks'])
for v in by.values():v.sort()
for c in cases:
 path=P/c['file'];assert sha(path)==c['sha256'];events={};times={}
 for name,d in [('production',production),('previous_best',previous),('candidate',combined),('candidate_current',combined_current),('coherent',coherent)]:
  mark=time.process_time();events[name],detail=d.decode(path,raw_events=True);times[name]=time.process_time()-mark
 mark=resource.getrusage(resource.RUSAGE_CHILDREN);run=subprocess.run([str(stream),'-s','2.4','-u','8'],input=path.read_bytes(),capture_output=True,timeout=30);assert run.returncode==0;end=resource.getrusage(resource.RUSAGE_CHILDREN);times['stream1090']=end.ru_utime+end.ru_stime-mark.ru_utime-mark.ru_stime
 lo=c['sample_start']*5+12000;hi=(c['sample_start']+c['sample_count'])*5-12000
 for source,rr in [('production',rows_prod),('previous_best',rows_prev),('candidate',rows_candidate),('candidate_current',rows_current)]:
  for e in events[source]+(events['coherent'] if source in ['production','previous_best'] else []):
   if e['source']=='broad_crc':continue
   tick=c['sample_start']*5+round(e['sample_4msps']*3)
   if lo<=tick<hi:rr.append(dict(e,ticks=tick,unix=c['unix']+(tick-c['sample_start']*5)/12e6,case=c['file']))
 for tick,msg in parse_avr(run.stdout,c['sample_start']):stream_raw.append(dict(ticks=tick,message_hex=msg,source='stream1090',case=c['file'],archive=c['archive']))
 cost.update(times);records.append(dict(file=c['file'],rf_seconds=c['rf_seconds'],cpu_seconds=times,events={k:len(v) for k,v in events.items()}))
 print(c['file'],times,flush=True)
# Preserve the original minimum. A thin archive may use an independently verified
# shared clock only if its observed anchors agree with that global calibration.
deltas=[];per_archive=collections.defaultdict(list)
for r in stream_raw:
 v=by[r['message_hex']];i=bisect.bisect_left(v,r['ticks']);close=v[max(0,i-1):i+1]
 if close and abs((t:=min(close,key=lambda t:abs(t-r['ticks'])))-r['ticks'])<=60000:deltas.append(t-r['ticks']);per_archive[r['archive']].append(t-r['ticks'])
offset=int(np.median(deltas)) if deltas else 0;mad=float(np.median(abs(np.array(deltas)-offset))) if deltas else 1e9
alignment={'anchors':len(deltas),'offset_ticks':offset,'mad_ticks':mad,'by_archive':{k:{'anchors':len(v),'median_ticks':float(np.median(v)),'mad_ticks':float(np.median(abs(np.array(v)-np.median(v))))} for k,v in per_archive.items()}}
write(OUT/(a.output.stem+'-stream-alignment.json'),alignment);assert len(deltas)>=100 and mad<=360,'Stream1090 alignment remains unverified'
assert all(abs(np.median(v)-offset)<=24 and np.median(abs(np.array(v)-offset))<=24 for v in per_archive.values()),'Cross-archive Stream clock disagreement'
cm={c['file']:c for c in cases};stream_events=[]
for r in stream_raw:
 c=cm[r['case']];tick=r['ticks']+offset
 if c['sample_start']*5+12000<=tick<(c['sample_start']+c['sample_count'])*5-12000:stream_events.append(dict(r,ticks=tick,unix=c['unix']+(tick-c['sample_start']*5)/12e6))
rows_prod+=stream_events;rows_prev+=stream_events
accepted_prod,prod_alignment,prod_guards=evaluate(stock,rows_prod,0,2**63);assert prod_alignment['verified'],prod_alignment
accepted_prev,prev_alignment,prev_guards=evaluate(stock,rows_prev,0,2**63);assert prev_alignment['verified'],prev_alignment
extra_prod,gprod=compare(rows_current,stock,actual,rows_prod+accepted_prod+annotations);extra_prev,gprev=compare(rows_candidate,stock,actual,rows_prev+accepted_prev+annotations)
def conflicts(rr):return [r for r in rr if not any(q['message_hex']!=r['message_hex'] and q['message_hex'][2:8]==r['message_hex'][2:8] and abs(q['ticks']-r['ticks'])<=48 for q in rows_prev+actual)]
extra_prod=conflicts(extra_prod);extra_prev=conflicts(extra_prev)
currentindex=index(rows_current);missing_current=[r for r in rows_prod if r['source'] not in ['coherent','stream1090'] and not nearby(currentindex,r['message_hex'],r['ticks'])];extindex=index(rows_candidate);missing=[r for r in rows_prev if r['source'] not in ['coherent','stream1090'] and not nearby(extindex,r['message_hex'],r['ticks'])]
def dist(r):
 v=[p for p in positions if p['icao']==r['message_hex'][2:8] and p['quality'] and p['available']<=r['unix'] and 0<=r['unix']-p['position_time']<=15];return max(v,key=lambda p:p['available'])['distance_nm'] if v else None
bins=collections.defaultdict(collections.Counter)
ranges=sorted((c['sample_start']*5+12000,(c['sample_start']+c['sample_count'])*5-12000,c) for c in cases);starts=[x[0] for x in ranges]
stock_core=[]
for r in stock:
 i=bisect.bisect_right(starts,r['ticks'])-1
 if i>=0 and r['ticks']<ranges[i][1]:
  c=ranges[i][2];stock_core.append(dict(r,unix=c['unix']+(r['ticks']-c['sample_start']*5)/12e6))
for name,rr in [('stock',stock_core),('production_extras',accepted_prod),('previous_best_extras',accepted_prev),('candidate_beyond_production',extra_prod),('candidate_beyond_previous_best',extra_prev)]:
 for r in rr:r['distance_nm']=dist(r);bins[distance_bin(r['distance_nm'])][name]+=1
seconds=sum(c['rf_seconds'] for c in cases);basecpu=cost['production']+cost['coherent']+cost['stream1090'];priorcpu=cost['previous_best']+cost['coherent']+cost['stream1090'];newcpu=cost['candidate']+cost['coherent']+cost['stream1090'];currentcpu=cost['candidate_current']+cost['coherent']+cost['stream1090'];digest=lambda rr:hashlib.sha256(json.dumps(sorted((r['ticks'],r['message_hex']) for r in rr)).encode()).hexdigest()
result={'hardware':platform.platform(),'candidate_sha256':sha(candidate),'baseline_methods':methods,'baseline_model_hashes':[sha(p) for p in paths],'previous_best_sha256':sha(best),'stream_binary_sha256':sha(stream),'rf_seconds':seconds,'effective_rf_seconds':sum(max(0,c['rf_seconds']-.002) for c in cases),'cases':records,'stream_alignment':alignment,'production_alignment':prod_alignment,'previous_alignment':prev_alignment,'production_guards':prod_guards,'candidate_guards':gprev,'production_extras':len(accepted_prod),'previous_best_extras':len(accepted_prev),'candidate_additions_beyond_production':len(extra_prod),'candidate_additions_beyond_previous_best':len(extra_prev),'candidate_events':extra_prev,'distance_bins':dict(bins),'raw_baseline_losses':len(missing),'raw_current_baseline_losses':len(missing_current),'raw_current_loss_events':missing_current,'raw_loss_events':missing,'add_only_losses':0,'cpu_seconds':dict(cost),'production_cpu_per_rf_second':basecpu/seconds,'previous_best_cpu_per_rf_second':priorcpu/seconds,'candidate_bundle_cpu_per_rf_second':newcpu/seconds,'current_plus_candidate_cpu_per_rf_second':currentcpu/seconds,'candidate_inference_after_current_cpu_per_rf_second':added_current.cpu/seconds,'candidate_current_windows':added_current.windows,'current_additions_digest':digest(extra_prod),'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024 if platform.system()=='Darwin' else 1),'incremental_candidate_inference_cpu_per_rf_second':added.cpu/seconds,'incremental_candidate_percent_of_production':100*added.cpu/basecpu,'candidate_windows':added.windows,'candidate_valid_window_outputs':added.valid,'production_digest':digest(accepted_prod),'previous_digest':digest(accepted_prev),'candidate_digest':digest(extra_prev),'far_stock_aircraft':len({r['message_hex'][2:8] for r in stock_core if r['distance_nm'] is not None and r['distance_nm']>=180}),'working_setup_changed':False,'scope':'Frozen candidate; all RF evaluation-only and interval-disjoint from training. Captured before freeze: no post-freeze prospective claim. Entire enabled serial algorithm union and actual relay plus conservative provisional-annotation mask. Annotation completeness is best-effort, not a full accepted-production ledger. CPU includes repeated serial frontend and per-clip Stream process startup; excludes live transport, not electrical power.'}
write(a.output,result);print(json.dumps({k:v for k,v in result.items() if k not in ['cases','candidate_events','raw_loss_events']},indent=2))

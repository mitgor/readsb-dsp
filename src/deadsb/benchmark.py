"""One frozen, offline bundle replay. Raw candidates are never accepted truth."""
import collections,hashlib,json,platform,subprocess,time
from pathlib import Path
from .policy import reduced

def benchmark(root,iq,output,profile=0):
 from rescue.runtime import RescueDecoder
 from rescue.pipeline_v3 import enable_v3,SequenceV3
 from rescue.model_cascade import cascade_decoder,production_paths
 from rescue.workers import merge_events
 import numpy as np
 root=Path(root);iq=Path(iq).resolve()
 if not iq.is_file() or iq.stat().st_size<2400 or iq.stat().st_size%2:raise ValueError('Expected nonempty UC8 at 2.4MS/s')
 if output.exists():raise ValueError('Choose a fresh output; never overwrite evaluation')
 d=cascade_decoder(production_paths(root),frontend='native',neural=True,broad_crc=False,methods=('timing','soft','matched'))
 enable_v3(d);h=json.loads((root/'models/pulse-sequence.json').read_text());d.coherent=SequenceV3(np.array(h['h_real'])+1j*np.array(h['h_imag']),d.optimized_backend,.35,48);d.coherent.sequence_enabled=False;d.coherent.acquisition_enabled=False;d.coherent.pair_retry=True
 # Use the same policy for both roles; cache restoration is verified in tests.
 mark=time.process_time();wall=time.perf_counter()
 with reduced(d,'dsp',{'level':profile}) as skip:
  if skip:events=[];work={}
  else:
   coherent=d.coherent
   if profile>=2:d.coherent=None
   try:
    with reduced(type('Coherent',(),{'decoder':coherent})(),'coherent',{'level':profile}):
     events,work=d.decode(iq,raw_events=True)
   finally:d.coherent=coherent
 cpu=time.process_time()-mark
 events=merge_events([[e for e in events if e['source']!='broad_crc']])
 # Public reports contain no aircraft payloads or positions.
 result=dict(project='deadsb dsp',hardware=platform.platform(),rf_seconds=iq.stat().st_size/4800000,profile=profile,cpu_seconds=cpu,wall_seconds=time.perf_counter()-wall,input_sha256=hashlib.sha256(iq.read_bytes()).hexdigest(),method_candidate_counts=dict(collections.Counter(e['source'] for e in events)),candidate_digest=hashlib.sha256(json.dumps([(e['sample_4msps'],e['message_hex'],e['source']) for e in events],separators=(',',':')).encode()).hexdigest(),candidate_count=len(events),guards='Raw candidate replay only; no independent truth, distance or incremental stock/relay comparison supplied.',live_changes=False)
 result['cpu_seconds_per_rf_second']=cpu/result['rf_seconds'];output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result

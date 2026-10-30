"""Historical reserved RF regression only, not prospective detection validation."""
import collections,hashlib,json,sys,time
from pathlib import Path
from rescue.runtime import RescueDecoder
from event_tap import EventTap
from async_relay import SOURCES
p=Path(sys.argv[1]);output=Path(sys.argv[2]);kwargs=dict(frontend='native',broad_crc=True,neural=False,methods=('timing','soft','matched'))
baseline=RescueDecoder('unused',**kwargs);cpu=time.process_time();old,_=baseline.decode(p,raw_events=True);baseline_cpu=time.process_time()-cpu
tapped=RescueDecoder('unused',**kwargs);rows=[];tap=EventTap(tapped,lambda r:rows.append(r));cpu=time.process_time();new,_=tapped.decode(p,raw_events=True);tap_cpu=time.process_time()-cpu;tap.close();assert old==new
identity=lambda r:(r['source'],r['sample_4msps'],r['message_hex'])
a=collections.Counter(identity(r) for r in old if r['source'] in SOURCES);b=collections.Counter(identity(r) for r in rows);assert a==b
report=dict(rf_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),rf_seconds=p.stat().st_size/4800000,raw_decoder_events=len(old),callback_events=len(rows),full_returned_event_dictionary_parity=True,allowed_event_multiset_parity=True,baseline_cpu_s=baseline_cpu,tap_cpu_s=tap_cpu,callback_counts=dict(tap.count),scope='Historical reserved RF, raw candidate regression with energy/CRC/timing/soft/matched only, not full current enabled pipeline or new detections. No model fitting or output forwarding; BroadCRC excluded from callbacks.')
output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

"""Aggregate-only report; private packet/model/RF evidence stays on Mac."""
import collections,hashlib,html,json,os,re
from pathlib import Path
from rescue.wire import BeastParser
ROOT=Path(__file__).resolve().parents[2];V=ROOT/'validation/energy-coherent-async-20261030';D=Path(os.environ.get('ADSB_NEURAL_DATA_ROOT','/Users/mit/Documents/!project/adsb-neural-rescue'))/'data/raw/energy-coherent-async-20261030/evidence'
r=json.loads((D/'result.json').read_text());private=json.loads((D/'result.private.json').read_text());capture=json.loads((D/'capture/capture.private.json').read_text());protected=json.loads((D/'protected.private.json').read_text());initial=json.loads((D/'attempt1/result.json').read_text());dedup=json.loads((D/'pi-dedup.json').read_text())
assert protected['error'] is None and protected['before']['pids']==protected['after']['pids'] and protected['before']['configs']==protected['after']['configs'] and protected['after']['fr24']['cfg_host']=='127.0.0.1:30005'
stock=sorted(capture['stock'],key=lambda r:r['arrival'])[:r['stock_records']];extra=collections.Counter((e['ticks']+2398,e['message_hex'],0) for e in private['emitted']);wire=(D/'output.beast').read_bytes();records=BeastParser(preserve_wire=True).feed(wire);observed_stock=[]
for row in records:
 k=(row['ticks_12mhz'],row['message_hex'],row['signal_byte'])
 if extra[k]:extra[k]-=1
 else:observed_stock.append(k)
expected_stock=[(e['ticks_12mhz'],e['message_hex'],e['signal_byte']) for e in stock]
assert observed_stock==expected_stock and not any(extra.values());assert len(records)==len(stock)+r['total']['emitted']
actual=[(e['message_hex'],e['ticks']) for b in capture['base'] for e in b['extra']]
def match(e,rows):return any(p==e['message_hex'] and abs(t-e['ticks'])<=1440 for p,t in rows)
audit=dict(stock_frame_order_payload_signal_timestamp_preserved=True,stock_records=len(stock),output_records=len(records),baseline_two_method_outside_recorded_full=sum(not match(e,actual) for e in private['baseline']),emitted_outside_recorded_full=r['total']['not_in_recorded_full_pipeline'],live_stock_only_fr24_unchanged=True,protected_pids_configs_models_sources_unchanged=True,sdrlost=protected['after']['stock']['samples_lost'],sdrdropped=protected['after']['stock']['samples_dropped'])
(V/'audit.json').write_text(json.dumps(audit,indent=2));(V/'result.json').write_text(json.dumps(r,indent=2));(V/'pi-dedup.json').write_text(json.dumps(dedup,indent=2));(V/'build.json').write_text((D/'build/build.json').read_text())
summary=dict(mode='isolated_not_deployed',methods=r['methods'],total=r['total'],stock=audit,complete_worker_cpu_s=r['complete_baseline_worker_cpu_s'],admission_cpu_s=r['admission_cpu_s'],dedup_cpu_s=r['final_dedup_cpu_s'],rust_microbenchmark_cpu_reduction_percent=100*(1-dedup['cpu_s']['rust']/dedup['cpu_s']['python']),source_queue_shed=r['counts'],earlier_repeat=initial['total'],cpu_quota_one_core_percent=35,rf_seconds=8,rf_kind='previously_reserved_engineering_replay',hardware='Pi5',fr24_stock_test_end_berlin='2026-11-01T20:00:00+01:00')
(V/'summary.json').write_text(json.dumps(summary,indent=2))
lines=['| Method | Complete two-method baseline | Retained | Estimated <=250ms | Median / p95 age |','|---|---:|---:|---:|---:|']
for s,v in r['methods'].items():lines.append(f"| {s} | {v['grouped_baseline']} | {v['retained_any_method']} | {v['under250_any_method']} | {v['retained_age_s']['median']*1000:.0f} / {v['retained_age_s']['p95']*1000:.0f} ms |")
md='''# Independent energy/coherent test with shared Rust deduplication

**Isolated only. No live switches or feeder routes changed.** Stock-only FR24 remains on port30005 until1November20:00Europe/Berlin; the existing combined pipeline, ADS-B Exchange, gain and collection stay unchanged. Target hardware reports Raspberry Pi5.

## Architecture

Two independent spawned processes consume immutable50ms UC8 chunks through separate bounded queues. Each has its own frontend/resampler/candidate work: coherent does not wait for energy to publish or finish its worker job. No neural, timing, soft, matched, acquisition, sequence, header, SIC, pulse, Stream1090 or broad-CRC work runs in the isolated decoders. Those methods remain unchanged in production.

Completed candidates pass original CRC/address/conflict/sample-clock/stock-progress admission. Coherent still needs sufficient causal rolling energy/stock evidence for alignment (20matches, median<=2us). That safety prerequisite is explicit; it is not a whole-second producer barrier. Startup unverified alignment fails closed.

A **single shared Rust final cache** sees original stock plus admitted energy and coherent extras. Five-second monotonic retention,100000entry cap, full14byte payload and RF timestamps within120us identify the same transmission across both filters. The five seconds is memory lifetime, not waiting time or payload-only suppression. The same payload transmitted again later survives. Stock frames always pass, including stock arriving after an already emitted extra; those races are counted. Epoch/unvalidated/stale inputs fail closed. Original RF timestamps are preserved. There is no final timestamp sorting or output holdback. Existing admission still screens stock duplicates; Rust is the one shared final transmission cache.

The experimental output is Beast bytes in owned RAM, never connected to FR24/readsb/ADSBx. This replay records captured CRC-valid stock DF17 only; it is not a new lossless test of every possible opaque/control Beast type.

## Pi results

Eight previously reserved RF seconds from completion-bridge-20261030 were replayed with fixed50ms dispatch, nice19/core3/CPUQuota35%/MemoryMax1GiB. Both worker processes share the one permitted CPU for this safety-limited test; they are independently asynchronous, not a two-core throughput benchmark. This is repeated engineering RF, not independent prospective evidence or parameter fitting.

'''+ '\n'.join(lines)+f'''

Final repeat: **{r['total']['emitted']}/{r['total']['baseline']}extras retained**, {r['total']['under250']}estimated below250ms. Every emitted extra matches both recorded production acceptance and the actual relay; zero unexplained additions. All{len(stock)}captured stock DF17frames preserve payload, signal byte, timestamp and order in the final Beast output. The shared Rust cache rejected{r['final_dedup'].get('cross_stream_duplicate_rejected',0)}cross-stream duplicates, with no capacity eviction or late-stock race in this sample. History ended with{r['final_history_entries']}entries.

The initial repeat retained{initial['total']['emitted']}/{initial['total']['baseline']}with{initial['total']['under250']}under250ms, energy median{initial['methods']['energy']['retained_age_s']['median']*1000:.0f}ms and coherent median{initial['methods']['coherent']['retained_age_s']['median']*1000:.0f}ms. The final repeat added full-baseline CPU instrumentation and an explicit final contract check; decoder parameters were unchanged. Both outcomes are preserved, not separate fresh validations.

The complete two-method baseline contains167of the210recorded full-pipeline extras (79.5%), or167/188excluding the separate Stream1090 source (88.8%). This is an eight-second coverage comparison, not a general guarantee. Arrival-order deduplication can change the credited method.

## CPU and queue pressure

Complete two-method worker computation (including jobs shed from the timed stream and evaluated later only for baseline coverage): energy{r['complete_baseline_worker_cpu_s']['energy']:.3f}CPU-s, coherent{r['complete_baseline_worker_cpu_s']['coherent']:.3f}CPU-s over8RF-s, together **{100*sum(r['complete_baseline_worker_cpu_s'].values())/8:.1f}%of one core at real time**. Worker demand alone exceeds the35%cap. Timed-stream admission adds{r['admission_cpu_s']:.3f}CPU-s; final Rust calls add{r['final_dedup_cpu_s']:.3f}CPU-s ({100*r['final_dedup_cpu_s']/8:.2f}%of one core at real time, including ctypes/call instrumentation). Shared CPU scheduling, input/coordination and admission remain additional costs.

Energy shed{r['counts'].get('energy_queue_shed',0)}/160chunks; coherent shed{r['counts'].get('coherent_queue_shed',0)}/160. One source being full does not stop the other source accepting a job. Median worker queue waits were{r['methods']['energy']['queue_wait_s']['median']*1000:.0f}ms and{r['methods']['coherent']['queue_wait_s']['median']*1000:.0f}ms respectively. All320jobs were eventually evaluated for a complete two-method baseline; those late baseline-only results were never emitted and their CPU is separated from timed-stream CPU. Timed replay lasted{r['wall_s']:.2f}s; that excludes later baseline completion.

These queue drops and latencies are not production losses: the live pipeline never used this copy. A reliable sub250ms claim is not supported. Ages are pre-feeder replay estimates based on RF sample offsets and original last-chunk readiness minus1.0005s; unmeasured USB/input timing and local socket delivery/cloud latency are excluded.

## Rust/reference checks

Three native Rust tests pass on Mac and Pi. A further50007event trace matches every Python-reference decision, counter and bounded history length, covering expiry,capacity,epoch changes, adjacent timestamp bins, unvalidated extras and late stock. A final-stage test passes on both platforms, checking cross-method suppression, repeated broadcasts, preserved late stock and invalid-CRC rejection.

Pi interface-inclusive100000event benchmark: Python{dedup['cpu_s']['python']:.3f}CPU-s versus Rust{dedup['cpu_s']['rust']:.3f}CPU-s, **{summary['rust_microbenchmark_cpu_reduction_percent']:.1f}%less CPU** for this trace. On Mac the call-by-call wrapper was similar/slightly slower; no universal speedup is claimed. Rust deduplication is not the dominant latency source here. All original guards remain before its input; CRC validity alone never authorizes a packet or a training label.

## Decision

**Keep this experimental.** The requested independent paths and shared final Rust cache work, but the35%one-core copy is undersized and sheds work. Reliable low latency needs adequate scheduling for the two workers and admission, or less frontend/guard cost; the normal production integration should reuse existing computation. Full independence deliberately duplicates frontend calculation. Keep the stock-only FR24 trial separate; no automatic deployment is scheduled.

Protected PIDs/config/source/model hashes, gain38.6dB, zeroSDRlost/dropped and capture limits passed. No persistent archive deletion, recorder flush or5GBcap change. RF, packet-level logs, model/source snapshots and both test repeats remain private on Mac. Only aggregate results are published.
'''
# Improve readability of compact numerical strings without changing values.
for a,b in {'port30005':'port 30005','until1November20:00Europe/Berlin':'until 1 November at 20:00 Europe/Berlin','Pi5':'Pi 5','immutable50ms':'immutable 50 ms','fixed50ms':'fixed 50 ms','20matches':'20 matches','median<=2us':'median <=2 us',',100000entry':', 100000-entry','full14byte':'full 14-byte','within120us':'within 120 us','All5655captured':'All 5655 captured','DF17frames':'DF17 frames','below250ms':'below 250 ms','under250ms':'under 250 ms','sub250ms':'sub-250 ms','the35%cap':'the 35% cap','the35%one-core':'the 35% one-core','over8RF-s':'over 8 RF-s','%of one core':'% of one core','minus1.0005s':'minus 1.0005 s','further50007event':'further 50007-event','Pi interface-inclusive100000event':'Pi interface-inclusive 100000-event','zeroSDRlost/dropped':'zero SDR lost/dropped','or5GBcap':'or 5 GB cap','gain38.6dB':'gain 38.6 dB','All320jobs':'All 320 jobs','contains167of the210recorded':'contains 167 of the 210 recorded','or167/188excluding':'or 167/188 excluding'}.items():md=md.replace(a,b)
md=re.sub(r'(?<=\d)(?=(?:CPU-s|RF-s|ms|chunks|entries|captured|cross-stream|extras|estimated|less CPU))',' ',md)
md=re.sub(r'(?<=[A-Za-z])(?=\d+\.\d+(?:CPU| CPU))',' ',md)
(V/'report.md').write_text(md)
def inline(s):return re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',html.escape(s))
parts=[];para=[];table=False
for line in md.splitlines()+['']:
 if line.startswith('|'):
  if para:parts.append('<p>'+inline(' '.join(para))+'</p>');para=[]
  if not table:parts.append('<table>');table=True
  if not line.startswith('|---'):parts.append('<tr>'+''.join('<td>'+html.escape(c.strip())+'</td>' for c in line.strip('|').split('|'))+'</tr>')
  continue
 if table:parts.append('</table>');table=False
 if not line:
  if para:parts.append('<p>'+inline(' '.join(para))+'</p>');para=[]
 elif line.startswith('#'):
  n=len(line)-len(line.lstrip('#'));parts.append(f'<h{n}>'+html.escape(line[n:].strip())+f'</h{n}>')
 else:para.append(line)
(V/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Energy/coherent async Rust test</title><style>body{background:#101b28;color:#e5edf5;font:16px/1.6 system-ui;max-width:1050px;padding:25px;margin:auto}table{border-collapse:collapse;display:block;overflow:auto}td{border-bottom:1px solid #405369;padding:10px}tr:first-child{font-weight:bold}h1,h2{color:#9edafa}</style>'+''.join(parts))
print(json.dumps(audit))

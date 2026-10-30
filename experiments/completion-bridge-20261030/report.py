"""Aggregate-only report; packet/model/RF evidence remains in private workspace."""
import html,json,os,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];V=ROOT/'validation/completion-bridge-20261030';P=Path(os.environ.get('ADSB_NEURAL_DATA_ROOT','/Users/mit/Documents/!project/adsb-neural-rescue'))/'data/raw/completion-bridge-20261030/evidence'
r=json.loads((V/'pi.json').read_text());private=json.loads((P/'pi.private.json').read_text());audit=json.loads((V/'reference-audit.json').read_text());health=json.loads((V/'protected-summary.json').read_text())
assert audit['exact_transmission_set_equal'] and audit['exact_attribution_set_equal'];assert not health['error'] and health['fr24_host']=='127.0.0.1:30005'
rows=[]
for source,v in r['methods'].items():
 ages=[]
 for b in private['full']:
  if b['source']!=source:continue
  a=[e['rf_age_s'] for e in private['emitted'] if b['message_hex']==e['message_hex'] and abs(b['ticks']-e['ticks'])<=1440]
  if a:ages.append(min(a))
 ages.sort();median=(ages[len(ages)//2]+ages[(len(ages)-1)//2])/2 if ages else None
 cpu=sum(c['work'].get('cpu_method_'+source+'_s',0) for c in r['cases'])
 rows.append(dict(method=source,baseline=v['full_replay'],retained_any_method=v['baseline_retained_any_method'],under250=v['baseline_retained_under250_any_method'],median_retained_age_s=median,first_completion_attribution=v['bridge_3s'],exclusive_worker_cpu_s=cpu))
summary=dict(decision='not_ready_no_deployment',hardware='Raspberry Pi 5 Model B',rf_seconds=8,methods=rows,total=r['total'],worker_cpu_s=r['worker_cpu_s'],bridge_cpu_s=r['bridge_cpu_s'],wall_s=r['wall_s'],reference=audit,protected=health,tests_mac=9,tests_pi=9,fr24_stock_test_end_berlin='2026-11-01T20:00:00+01:00',limits=['35%one-core quota is below standalone DSP replay CPU requirement','Repeated engineering RF, not independent prospective evidence','Stream1090 is a separate producer, not covered','Timing is pre-transport replay estimation; no USB or RF-to-cloud latency measurement'])
(V/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
table=['| Baseline method | Full replay extras | Retained <=3s, any completion | <=250ms | Median retained age | Exclusive method CPU-s |','|---|---:|---:|---:|---:|---:|']
for v in rows:table.append(f"| {v['method']} | {v['baseline']} | {v['retained_any_method']} | {v['under250']} | {v['median_retained_age_s']:.3f}s | {v['exclusive_worker_cpu_s']:.3f} |")
md='''# Per-completion bridge: isolated Pi validation

Implemented and tested, **not ready for deployment**. FR24 remains direct stock on port 30005 through 1 November at 20:00 Berlin. Working DSP, combined relay, ADS-B Exchange and collection remain unchanged. Target hardware reports **Raspberry Pi 5**, despite older Pi4 references.

## Results

Eight fresh contiguous RF seconds were captured from the idle optional mirror, checksum-transferred and reserved evaluation-only before replay. No SDR access, persistent recorder flush, model fitting or feeder injection. This is repeated engineering evaluation, not independent prospective validation.

The unchanged grouped replay exactly reproduces all 188production worker-pool extras, **including payload, sample timestamp and method attribution**. The other 22production extras are Stream1090, a separate producer outside this pool bridge. They are not decoder replay misses.

Final capped target run retained 58/188 extras (30.9%) within the diagnostic 3 s ceiling, **0/188 below 250 ms**. All 58 match actual production admissions and relay transmissions; zero new unexplained transmissions. The normal grouped output retains all 188; only the isolated early-admission branch loses packets. No live output is affected.

'''+ '\n'.join(table)+'''

Retention is attributed to each packet's baseline method even when a different method completes first. The actual first-completion emission attribution is energy 11 / timing 1 / soft 3 / matched 2 / coherent 41 / neural 0: adding these to the baseline counts would double-count transmissions. For example, six baseline neural packets survived through another earlier completion.

## CPU and latency interpretation

'''+f"Worker computation: **{r['worker_cpu_s']:.3f} CPU-s  / 8 RF-s = {100*r['worker_cpu_s']/8:.1f}% of one core at real time**. Admission bridge: **{r['bridge_cpu_s']:.3f} CPU-s  / 8 RF-s = {100*r['bridge_cpu_s']/8:.1f}% of one core**. These together require about{100*(r['worker_cpu_s']+r['bridge_cpu_s'])/8:.1f}% of one core, before remaining coordination/I/O. The entire copied observer was capped at 35% of one core, nice 19 / core 3 / 1 GiB, so backlog is expected. Replay wall time was{r['wall_s']:.2f}s. Method CPU columns are exclusive measured attribution; shared frontend, CRC quarantine and overhead are additional. CPU time is not electrical power.\n\n"+'''
This deliberately restricted full decoder copy cannot establish sub-250 ms production performance. Production uses multiple existing workers; the intended bridge would reuse their results, not duplicate inference. No lower live CPU or production latency claim is made. CPU utilization is scheduling-sensitive: the preceding engineering run retained 73/188 under the same cap; the final old-epoch-safety repeat retained 58/188. Both retained zero under 250 ms. This variability is preserved rather than selecting the better run.

Ages are estimated pre-transport event-to-admission times on a real-time-paced replay. RF time is anchored to original final-batch readiness minus 1.0005 s; USB buffering and earlier input latency are not measured. The old tap wall timestamp is roughly 33 ms later than this availability-derived origin. Do not interpret these as antenna-to-output or RF-to-cloud measurements, or compare them directly with the earlier unconstrained production observer medians.

## Implementation and safeguards

`CompletionPool` copies raw completed-future events before the ordered whole-second grouping stage. A slow coherent future does not block a completed DSP future. Original grouping/statistics/collection output remains intact. Raw seam candidates must not be pre-deduplicated: the original merge is non-transitive.

`Bridge` reuses unchanged production admission on indexed stock history, causal rolling energy anchors and a stock-progress watermark. It retains CRC, 20 alignment matches/median <=2 us, prior-stock address, conflict, 120 us duplicate and bounded 5 RF-second shared history checks. Pending anchor windows survive stock progress until their admission deadline; expiry remains explicit. The input owner explicitly changes epochs, preventing late old futures from resetting the bridge. Epoch/alignment failures fail closed. Original timestamps are never rewritten. Broad CRC predictions remain quarantined.

An optional `publish_to` adapter submits individual guarded events to the experimental AsyncFanIn. It opens no sockets and is not attached to any feeder. The target measurements stop at admission; additional TCP-delivery latency is not included. Stream1090 needs a separate guarded completion adapter before this covers the full pipeline.

Nine tests pass on Mac and Pi: independent completion, raw seam preservation, watermark gating, shared deduplication, out-of-order completion, pending-anchor retention, actual CRC/address/conflict gates, old epoch rejection and publication field preservation (some checks share test cases). Frozen source/model hashes, protected PIDs/configs, gain 38.6 dB, zero SDR lost/dropped counters, stock-only FR24 route and capture limits passed. The optional mirror was released normally. No 5 GB cap, retention or normal 12-hour flush schedule changed.

## Engineering history and next gate

The first target attempt failed an overly short replay-harness deadline; its evidence is retained. A second separated-window diagnostic exposed overly aggressive anchor eviction and is not a continuous performance result. Contiguous capped attempts 3/4 preserve their different scheduling outcomes. Decoder arithmetic, weights and admission thresholds were not tuned on RF. All source/data evidence remains private on Mac.

**Keep production unchanged.** A safe next gate is controlled shadow integration that reuses existing worker results, with indexed/shared admission profiling, complete Stream1090 coverage and measured source-to-admission p50/p95/p99. It requires validation at the real production scheduling topology rather than treating this 35% duplicate observer as its latency predictor. Any later trial must preserve the ongoing FR24 stock-only comparison and separately validate actual FR24 behavior.
'''
(V/'report.md').write_text(md)
def inline(s):
 s=html.escape(s);s=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',s);return re.sub(r'`(.+?)`',r'<code>\1</code>',s)
# Render this report's simple paragraphs/headings/table without a markdown dependency.
lines=md.splitlines();parts=[];paragraph=[];in_table=False
for line in lines+['']:
 if line.startswith('|'):
  if paragraph:parts.append('<p>'+inline(' '.join(paragraph))+'</p>');paragraph=[]
  if not in_table:parts.append('<table>');in_table=True
  if line.startswith('|---'):continue
  parts.append('<tr>'+''.join('<td>'+html.escape(c.strip())+'</td>' for c in line.strip('|').split('|'))+'</tr>');continue
 if in_table:parts.append('</table>');in_table=False
 if not line.strip():
  if paragraph:parts.append('<p>'+inline(' '.join(paragraph))+'</p>');paragraph=[]
 elif line.startswith('#'):
  n=len(line)-len(line.lstrip('#'));parts.append(f'<h{n}>'+html.escape(line[n:].strip())+f'</h{n}>')
 else:paragraph.append(line)
(V/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Completion bridge: Pi validation</title><style>body{background:#101b28;color:#e3edf5;font:16px/1.6 system-ui;max-width:1100px;margin:auto;padding:25px}table{border-collapse:collapse;width:100%;display:block;overflow:auto}td{padding:10px;border-bottom:1px solid #435465}tr:first-child{font-weight:bold}h1,h2{color:#9cdbfa}</style>'+''.join(parts))
print(json.dumps(summary,indent=2))

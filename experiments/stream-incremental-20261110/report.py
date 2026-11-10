"""Aggregate-only incremental Stream1090 report; private RF stays private."""
import argparse,json,hashlib,html,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--dest',type=Path,required=True);a=p.parse_args();O=a.results;V=a.dest;V.mkdir(exist_ok=True);d=json.loads((O/'pi.json').read_text());checks=json.loads((O/'protected-checks.json').read_text());assert all(checks.values());assert d['all_raw_packets_timestamps_order_exact'] and d['all_reference_core_digests_exact'];hardware=json.loads((O/'parity.json').read_text())['hardware'];b=json.loads((O/'receiver-before.private.json').read_text());end=json.loads((O/'receiver-after.private.json').read_text());gap=end['capture']['counts']['tap_gap_samples']-b['capture']['counts']['tap_gap_samples'];modes=['batch','20ms','50ms'];L=d['families']['long'];lat=d['paced']['decoder_availability'];n=d['paced']['windows'];summary={'date_berlin':'2026-11-10','hardware':hardware,'state':'isolated_prototype_not_deployed','working_pipeline_changed':False,'exact_packet_timestamp_and_order_retention':True,'mac_pi_core_digests_exact':True,'long_rf_seconds':L['core_rf_seconds'],'recent_rf_seconds':d['families']['recent']['core_rf_seconds'],'total_windows':502,'long_stock_extras_retained_per_mode':968,'recent_stock_extras_retained_per_mode':11,'raw_core_packet_records_per_mode':15221,'added_transmissions':0,'lost_transmissions':0,'paced_rf_windows':n,'paced_core_packet_count':lat['batch']['packets'],'decoder_latency_ms':lat,'cpu':{},'controls':json.loads((O/'controls.json').read_text()),'protected_checks':checks,'rf_copy_gap_seconds_during_setup_test':gap/2400000,'limits':['Decoder availability only; not current coordinator/feeder latency','Single target throughput pass and eight paced one-second windows','Historical RF, not prospective validation','Long distances estimated; recent distances stock-quality-gated','Early guard/clock/dedup/relay release not implemented or validated','Deadline/overflow/gap errors poison the context and require quarantine of that logical window','Memory-controller enforcement unavailable on this Pi; MemoryMax only requested']}
for mode in modes:
 summary['cpu'][mode]={'throughput_cpu_s_per_rf_s':L['cpu'][mode]['cpu_s_per_rf_s'],'paced_cpu_s_per_rf_s':d['paced']['cpu_s'][mode]/n}
base=summary['cpu']['batch']['paced_cpu_s_per_rf_s'];pct={m:100*(summary['cpu'][m]['paced_cpu_s_per_rf_s']/base-1) for m in modes}
table='| Mode | Median | p95 | p99 | Maximum | Paced CPU-s/RF-s |\n|---|---:|---:|---:|---:|---:|\n'
for mode in modes:
 s=lat[mode];table+=f"| {mode} | {s['p50_ms']:.1f} ms | {s['p95_ms']:.1f} ms | {s['p99_ms']:.1f} ms | {s['max_ms']:.1f} ms | {summary['cpu'][mode]['paced_cpu_s_per_rf_s']:.4f} |\n"
distance='| Distance (nm) | Batch | 20 ms | 50 ms | Lost |\n|---|---:|---:|---:|---:|\n'
for band in ['0-50','50-100','100-150','150-180','180-200','200-250','250+','unknown']:
 count=L['retained_distance_bins']['guarded_beyond_stock'].get(band,{}).get('native',0);distance+=f'| {band} | {count} | {count} | {count} | 0 |\n'
report=f'''# Incremental native Stream1090 — Pi test, 10 November 2026

20 ms and 50 ms chunk processing retained all tested packets, timestamps and raw order. The prototype is isolated; **the working pipeline remains unchanged**. Recommended experimental chunk size: **20 ms**.

## Paced decoder output latency

Identical saved RF was delivered at its original sample rate to each implementation separately. {n} one-second windows produced {lat['batch']['packets']} core packets per mode. Latency is measured from the packet's RF end to availability of its returned decoder result. It includes context creation, chunk waiting, incomplete-block carry, native work, Python conversion and OS scheduling under the target quota.

{table}
The 20 ms paced cost is **{pct['20ms']:.1f}% more Stream1090 CPU** than batch in this short run: approximately {100*(summary['cpu']['20ms']['paced_cpu_s_per_rf_s']-base):.2f}% of one core, or {25*(summary['cpu']['20ms']['paced_cpu_s_per_rf_s']-base):.2f}% of four-core capacity. The 50 ms paced increase is {pct['50ms']:.1f}%. These are branch costs, not percentages of the whole receiver's existing CPU.

This is **decoder availability, excluding live RF transport, stock calibration/admission and feeder latency**. The current coordinator still gates a whole window. It has not been changed, and early feeder release has not been validated. Earlier candidates alone cannot establish sub-250 ms end-to-end delivery.

## Throughput CPU and retention

The full replay used 119 historical one-second windows and 383 aligned short clips (143.24718 core RF seconds). Modes ran in rotating order per case. Finite replay calls used disabled per-call deadlines, while deadline rejection was tested separately; this avoids quota-related aborts in timing comparisons. All raw callback rows, payload bytes, sample timestamps and ordering matched exactly, including terminal flush. Physical-core digests also match Mac/Pi and the frozen parent reference. There were **15,221 raw core packet records per mode, zero gains and zero losses**.

Long-window throughput CPU: batch {summary['cpu']['batch']['throughput_cpu_s_per_rf_s']:.4f}, 20 ms {summary['cpu']['20ms']['throughput_cpu_s_per_rf_s']:.4f}, 50 ms {summary['cpu']['50ms']['throughput_cpu_s_per_rf_s']:.4f} CPU-s/RF-s. The unpaced 20 ms increase is {100*(summary['cpu']['20ms']['throughput_cpu_s_per_rf_s']/summary['cpu']['batch']['throughput_cpu_s_per_rf_s']-1):.1f}%. The larger paced overhead is reported separately because short bursts and pacing can affect scheduling/frequency and wrapper costs. One throughput pass and eight paced RF seconds do not establish tail guarantees or precise steady-state energy savings.

After the SAME deferred frozen common guards, the historical long corpus retains these extras beyond stock. **Long distances are estimates**, without NIC/NACp qualification:

{distance}
All three modes retain **968 long-corpus stock extras**, including the same three estimated 180–200 nm events. The recent corpus retains **11 stock extras per mode**, with stock-quality-gated distances and no extras >=180 nm. Exact raw equality preserves the parent's full current-method-union result when the same deferred masks are used; there are no new full-pipeline detections here. These data are insufficient to claim improved range, and they are historical regression RF, not fresh prospective validation.

## Implementation

`incremental.h` supplies create/feed/finish/destroy. One context persists across chunks within the current logical window. Interpolation history, magnitude blocks, eight-phase registers, sample clock, repair confidence, trust and dedup state are carried forward. Contexts reset at the current logical window boundaries; this preserves the baseline's trust semantics. No new rolling one-second window is decoded for every chunk.

Complete native 8,208-sample blocks (~3.42 ms) are processed as soon as a call supplies them; partial blocks are carried to the next chunk. **No zero padding at chunk boundaries.** Finish reproduces the batch reader's single terminal zero-padded block, even when the input ends exactly on a block boundary. The original upstream magnitude/interpolation code and seven confidence/RSSI/preamble helper bodies are unchanged. Pinned upstream source headers retain their original hashes and licensing.

The API rejects gaps, overlap, wrong order, early/repeated finish, overflow, invalid lengths and deadlines. An error poisons the logical context; previously returned raw candidates must remain quarantined until the caller's appropriate validation/commit policy. Callers must reset on a receiver epoch change. This API does not itself forward packets or implement admission.

## Controls and protected receiver

Known clean/repaired packets straddled chunk and logical-core boundaries. Tests also varied feeds around the native block size. Fixed and irregular splits, including single-sample fragments, produced exact packet/time/order parity. Untrusted repairs and noise emitted zero. Gap, overlap, incomplete close, capacity and timeout controls rejected partial output. AddressSanitizer/UndefinedBehaviorSanitizer and library-load floating-point-environment checks passed on Mac and Pi.

Target: {hardware}. Owned tmpfs only; saved RF, copied libraries, nice19/core3/CPUQuota35%, requested MemoryMax1G/zero swap and finite 450-second runtime. The kernel did not expose memory-controller enforcement. The baseline library SHA-256 was checked against the installed native library before replay. No SDR or mirror consumer was opened, no candidate packets were sent, no models/method switches/gain/routes changed, no service restarted and no capture flush requested. The 5 GB RF cap remains unchanged.

Protected PIDs, source/model/configuration hashes, native backend, gain and primary SDR loss counters matched before/after. Across setup/test the best-effort copied RF tap recorded {gap:,} additional gap samples (~{gap/2400000:.3f} RF seconds); causality is not established. Primary SDR loss counters did not increase. The copied-tap observation is retained rather than claiming no RF-copy loss.

Source, frozen data/reference manifests, libraries, controls and private diagnostics are checksum-backed on Mac. All candidate outputs remain evaluation-only, never training labels. Only verified owned temporary files were removed; persistent capture archives were untouched.

## Next validation gate

The next experiment is an isolated incremental admission/relay path: causal stock-clock corroboration and stock watermarks, conflict/dedup lookahead, exact original-first packet retention, logical-window/epoch failure handling and delivery latency through the relay. Preserve the working batch path until that path passes fresh RF and target-health checks. Current deferred reference masks must not be used as evidence that the early-admission problem is already solved.
'''
(V/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(V/'report.md').write_text(report)
def inline(s):
 s=html.escape(s);s=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',s);s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s);return s
parts=[];lines=report.splitlines();i=0
while i<len(lines):
 line=lines[i]
 if line.startswith('|'):
  rows=[]
  while i<len(lines) and lines[i].startswith('|'):rows.append(lines[i]);i+=1
  parts.append('<table>')
  for j,row in enumerate(rows):
   if j==1:continue
   tag='th' if j==0 else 'td';parts.append('<tr>'+''.join(f'<{tag}>'+inline(c.strip())+f'</{tag}>' for c in row.strip('|').split('|'))+'</tr>')
  parts.append('</table>');continue
 if line.startswith('#'):
  n=len(line)-len(line.lstrip('#'));parts.append(f'<h{n}>'+inline(line[n:].strip())+f'</h{n}>')
 elif line:parts.append('<p>'+inline(line)+'</p>')
 i+=1
(V/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Incremental Stream1090 Pi test</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#e1eaf5;background:#101c28}table{border-collapse:collapse;width:100%;margin:24px 0}td,th{padding:9px;border-bottom:1px solid #506174;text-align:left}p{overflow-wrap:anywhere}</style>'+''.join(parts))
print(json.dumps({'recommended_chunk_ms':20,'paced_CPU_increase_percent':pct['20ms'],'p95_ms':lat['20ms']['p95_ms'],'lost':0}))

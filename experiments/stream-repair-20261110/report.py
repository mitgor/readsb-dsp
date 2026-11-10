"""Generate public aggregate report from private frozen outputs; no receiver I/O."""
import argparse,json,statistics,html,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--dest',type=Path,required=True);a=p.parse_args();O=a.results;V=a.dest;V.mkdir(exist_ok=True)
paths=sorted(O.glob('pi-[123].json'));assert paths,'No completed Pi pass';runs=[json.loads(p.read_text()) for p in paths];r=runs[0]
for q in runs:
 assert all(q['digests'][k+'_native']==q['digests'][k+'_executable'] for k in ['raw','guarded','actual_extra'])
 assert q['digests']==r['digests'],'Repeat output drift'
health=json.loads((O/'health.private.json').read_text());checks=json.loads((O/'protected-checks.json').read_text());assert all(checks.values());assert health['production_actions']==[]
summary={'date_berlin':'2026-11-10','hardware':health['hardware'],'completed_pi_passes':len(runs),'working_pipeline_changed':False,'families':{},'protected_checks':checks,'synthetic_controls':json.loads((O/'repair-controls.json').read_text()),'noise_clean_controls':json.loads((O/'controls.json').read_text()),'exact_native_executable_packet_timestamp_parity':True,'exact_pi_repeat_parity':True if len(runs)>1 else None,'repeat_variance_estimated':len(runs)>1,'floating_point_environment_unchanged_on_load':True,'mac_pair_exact':True,'library_sha256':r['native_library_sha256'],'executable_sha256':r['executable_sha256'],'recent_full_pipeline_attribution':{k:v for k,v in json.loads((O/'pi-1-attribution.json').read_text()).items() if k!='new_native_rows'},'limits':['Historical regression replay, not prospective range validation','Long distances estimated; recent positions quality-gated','C++ in-process extension using pinned upstream core, not a C rewrite','Not yet bound into live readsb deadline/admission path','RF file reads and full receiver CPU excluded','Memory controller unavailable; requested MemoryMax is not verified enforcement']}
for family in ['long','recent']:
 d=r['families'][family];summary['families'][family]={k:v for k,v in d.items() if k!='cpu'};cost={}
 for name in ['native','executable']:
  v=[q['families'][family]['cpu'][name]['decode_plus_guard_cpu_s_per_rf_s'] for q in runs];cost[name]={'median_cpu_s_per_rf_s':statistics.median(v),'minimum':min(v),'maximum':max(v),'per_pass':v}
 summary['families'][family]['cpu']=cost
 summary['families'][family]['cpu_reduction_percent']=100*(1-cost['native']['median_cpu_s_per_rf_s']/cost['executable']['median_cpu_s_per_rf_s'])
L=summary['families']['long'];n=L['cpu']['native']['median_cpu_s_per_rf_s'];e=L['cpu']['executable']['median_cpu_s_per_rf_s'];saving=L['cpu_reduction_percent'];recent=summary['families']['recent'];c=L['counts']['guarded_beyond_stock'];table='| Distance (nm) | Extended native | Current executable | Lost |\n|---|---:|---:|---:|\n'
for b in ['0-50','50-100','100-150','150-180','180-200','200-250','250+','unknown']:
 z=L['distance_bins']['guarded_beyond_stock'].get(b,{});table+=f"| {b} | {z.get('native',0)} | {z.get('executable',0)} | {z.get('executable_only',0)} |\n"
table+=f"| **Total** | **{c['native']}** | **{c['executable']}** | **{c['executable_only']}** |\n"
report=f'''# Native Stream1090 repair and trust — Pi validation, 10 November 2026

The extended native library retained every measured executable DF17 recovery and timestamp, using **{saving:.1f}% less method CPU** on the primary saved-RF replay. The live pipeline remains unchanged. This is a separate in-process C++20 library with a C ABI, reusing the pinned upstream core; the existing clean-CRC C subset is unchanged.

## Recovery by distance

119 uniformly selected one-second historical RF windows with complete paired references, identical input to both implementations. Counts are guarded, deduplicated extras beyond stock. **Historical distances are estimates** without NIC/NACp qualification.

{table}
All {c['native']} extras were shared. The earlier clean-only C subset recovered 214 on this same RF; the extension now retains the executable's repair/trust recovery. Native and executable also matched all raw unique DF17 transmissions and all sample timestamps exactly on Pi. Against historical recorded unified output both added 61 candidates; this historical reference is not the full current pipeline.

## Pi CPU

{len(runs)} complete paired passes, alternating execution order per RF case. CPU includes native allocations, buffer conversion and common guards, or executable startup, child CPU, pipes, AVR parsing and the same guards. Raw RF file reads are excluded.

| Measurement | Extended native | Executable |
|---|---:|---:|
| Median CPU seconds per RF second | {n:.4f} | {e:.4f} |
| Minimum–maximum across passes | {L['cpu']['native']['minimum']:.4f}–{L['cpu']['native']['maximum']:.4f} | {L['cpu']['executable']['minimum']:.4f}–{L['cpu']['executable']['maximum']:.4f} |
| Equivalent one-core usage at real time | {100*n:.2f}% | {100*e:.2f}% |
| CPU milliseconds per guarded stock extra | {1000*n*119/c['native']:.1f} | {1000*e*119/c['executable']:.1f} |

The saving is {100*(e-n):.2f}% of one core, approximately {25*(e-n):.2f}% of total four-core capacity. It is not a {saving:.1f}% reduction of the complete receiver's CPU. Savings include avoiding process/pipe/formatting overhead and computing no unused export RSSI, not a claimed new error-correction algorithm. Live scheduling latency was not tested.

## Recent complete-pipeline supplement

383 aligned short clips, 24.24718 RF seconds after edge trimming. Both implementations recovered 11 guarded extras beyond stock and two beyond the frozen current other-DSP replay, one at 50–100 nm and one at 100–150 nm. Neither added a packet beyond the full current union once current Stream1090, actual unified output and annotations were included: **zero gains and zero losses**. No additional recovery beyond 180 nm was established. All candidate output remains quarantined; nothing becomes training labels or feeder input.

Recent short-clip median CPU was {recent['cpu']['native']['median_cpu_s_per_rf_s']:.4f}/{recent['cpu']['executable']['median_cpu_s_per_rf_s']:.4f} CPU-s/RF-s, native/executable. Short clips magnify executable startup and cold trust state, so use the one-second primary corpus for deployment expectations. Recent ranges require causal stock NIC/NACp >=5, age <=15 seconds and no MLAT/TIS-B. Three historical estimated 180–200 nm extras were retained, but distant opportunity coverage is too small for a range-improvement claim.

## Implementation and safety checks

The extension uses unmodified dependencies from [Stream1090](https://github.com/mgrone/stream1090) commit `2189bdaca1d62d5e88600b21a281ccc5c18012f2`; upstream GPL notices, license and SHA-256 provenance are included. It preserves:

- the exact 2.4-to-8 MHz frontend and eight-phase rolling framing;
- syndrome-table repairs, confidence-ranked bounded erasure repair, and DF19 repair;
- DF11 and other internal formats that affect trust, ICAO+capability keys, trust TTL, phase suppression and duplicate behavior;
- separate sightings before trust, with repaired candidates unable to seed new trust;
- per-window state reset and final partial-block zero-padding, matching current executable invocation.

Only DF17 is exported, matching current rescue admission. The C ABI returns explicit invalid-input, overflow and exception errors, with no usable output on error. Fast-math is applied only when compiling the native object, never at shared-library link time: a load-time floating-point-environment check passes on Mac and Pi. The earlier direct-link build had a `crtfastmath` initializer and was replaced before these final measurements. It creates no child process, SDR/mirror consumer, feeder connection or signal handler. Nothing in the normal readsb build enables it.

Known synthetic single-bit, adjacent two-bit, three-bit burst and DF19 repairs matched executable packets/timestamps exactly. Trusted cases recovered the known packet; damaged-only untrusted cases emitted zero. Clean and pure-noise controls passed. Direct trust-separation/expiry and non-table syndrome-solver tests passed under AddressSanitizer/UndefinedBehaviorSanitizer on Mac; API sanitizer tests covered successful decoding, invalid input and overflow. These verify implementation behavior, not correctness of every repaired real-world packet.

Stock alignment was independently calibrated for each implementation from the same RF (769 ticks). Physical RF-core trimming separately uses the frozen original-C baseline's measured stock-to-preamble offset of 2,400 ticks. An initial harness version conflated those origins; its matching paired outputs are retained only as a coordinate audit and excluded from final CPU/recovery results. Native/executable packet/timestamp digests match exactly on Pi. The final safe-link build has one complete paired pass; repeat variance is not estimated. Earlier coordinate/link-audit runs are preserved but excluded from the final performance table. Mac native/executable pairing also matches exactly. Mac/Pi digests are checked separately; target pairing is authoritative.

Target: {health['hardware']}. Isolated owned tmpfs, nice 19, core 3, CPUQuota 35%, finite 900-second unit, requested MemoryMax 1 GiB and zero swap. The kernel did not expose memory-controller enforcement. Protected receiver/feeder PIDs, method switches, models, library/source hashes, gain, configurations and SDR loss counters remained unchanged; the 5,000,000,000-byte RF cap and normal disk-save schedule were preserved. No live route, service, model or logging change was made.

## Limits and next gate

This validates a native finite-window replacement core against the current executable on saved RF. It does not yet validate a live readsb binding, cancellation/deadline behavior, pending-queue integration or prospective distant RF. The smaller original C path and production executable remain unchanged. Preserve stock-first validation and downstream conflict/dedup guards if integrating later. Historical evaluation intervals stay reserved; outputs are not supervised labels.

Reproducible code and private input/output manifests are retained under the dated experiment. Public summary contains aggregates only; raw RF, packet-level records, receiver diagnostics and credentials remain private. The owned Pi work is removed only after checksum-verified durable Mac backup.
'''
if len(runs)==1:
 report=report.replace('Median CPU seconds per RF second','CPU seconds per RF second').replace('1 complete paired passes','One complete paired pass')
 report='\n'.join(line for line in report.split('\n') if not line.startswith('| Minimum–maximum across passes'))
(V/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(V/'report.md').write_text(report)
def inline(s):
 s=html.escape(s)
 s=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',s)
 s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
 s=re.sub(r'\[([^\]]+)\]\((https://[^)]+)\)',r'<a href="\2">\1</a>',s)
 return s
parts=[];lines=report.splitlines();i=0
while i<len(lines):
 line=lines[i]
 if line.startswith('|'):
  table=[]
  while i<len(lines) and lines[i].startswith('|'):table.append(lines[i]);i+=1
  parts.append('<table>')
  for j,row in enumerate(table):
   if j==1:continue
   tag='th' if j==0 else 'td';parts.append('<tr>'+''.join(f'<{tag}>'+inline(c.strip())+f'</{tag}>' for c in row.strip('|').split('|'))+'</tr>')
  parts.append('</table>');continue
 if line.startswith('#'):
  level=len(line)-len(line.lstrip('#'));parts.append(f'<h{level}>'+inline(line[level:].strip())+f'</h{level}>')
 elif line:parts.append('<p>'+inline(line)+'</p>')
 i+=1
(V/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Native Stream1090 repair/trust Pi validation</title><style>body{font:16px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:0 20px;background:#101c28;color:#e4edf6}table{border-collapse:collapse;width:100%;margin:24px 0}td,th{padding:10px;border-bottom:1px solid #526174;text-align:left}p{overflow-wrap:anywhere}</style>'+''.join(parts))
print(json.dumps({'passes':len(runs),'cpu_reduction_percent':saving,'native_cpu':n,'executable_cpu':e,'extras':c}))

"""Build only sanitized aggregate report; never publishes packets or snapshots."""
import argparse,html,json
from pathlib import Path

def render(text):
 import re
 def inline(s):return re.sub(r'\*\*(.*?)\*\*',r'<strong>\1</strong>',html.escape(s))
 parts=[];para=[];table=False
 def flush():
  if para:parts.append('<p>'+inline(' '.join(para))+'</p>');para.clear()
 for line in text.splitlines():
  if line.startswith('|'):
   flush()
   if not table:parts.append('<div class="scroll"><table>');table=True
   cells=[x.strip() for x in line.strip('|').split('|')]
   if all(re.fullmatch(r'[: -]+',c) for c in cells):continue
   parts.append('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in cells)+'</tr>');continue
  if table:parts.append('</table></div>');table=False
  if not line.strip():flush();continue
  if line.startswith('#'):
   flush();n=len(line)-len(line.lstrip('#'));parts.append(f'<h{n}>'+inline(line[n:].strip())+f'</h{n}>')
  else:para.append(line)
 flush()
 return '<!doctype html><meta charset="utf-8"><title>Incremental Stream1090 admission</title><style>body{background:#101b28;color:#e7eff7;font:16px/1.55 system-ui;max-width:1120px;margin:40px auto;padding:0 24px}table{border-collapse:collapse;width:100%;font-size:14px}td{border-bottom:1px solid #40536b;padding:9px;text-align:right}td:first-child{text-align:left}tr:first-child{font-weight:bold;background:#213047}.scroll{overflow:auto}h2{margin-top:2em}</style>'+''.join(parts)

def main():
 p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=True,parents=True)
 mac=json.loads((a.private/'mac-indexed.json').read_text());pi=json.loads((a.private/'pi-indexed.json').read_text());attribution=json.loads((a.private/'pi-indexed-attribution.json').read_text());health=json.loads((a.private/'pi-indexed-health.private.json').read_text());rows=[]
 for platform,j in [('Mac',mac),('Pi',pi)]:
  for r in j['results']:
   for source in ['stream1090','energy','all']:
    m=r['metrics'][source];v=m['latency'];rows.append(f"| {platform} | {r['mode']} | {source} | {m['emitted']} | {m['early']} / {m['fallback']} | {v.get('p50_ms',0):.1f} | {v.get('p95_ms',0):.1f} | {v.get('max_ms',0):.1f} | {v.get('under250',0)} |")
 cpu=[];cpu_notes=[]
 for platform,j in [('Mac',mac),('Pi',pi)]:
  b,i=j['results'];delta=100*(i['cpu_s_per_RF_s']/b['cpu_s_per_RF_s']-1)
  for r in j['results']:cpu.append(f"| {platform} | {r['mode']} | {r['cpu_s_per_RF_s']:.4f} | {r['worker_cpu_s']['native']/8:.4f} | {r['worker_cpu_s']['energy']/8:.4f} | {r['worker_cpu_s']['admission_main']/8:.4f} |")
  cpu_notes.append(f"{platform}: incremental total process CPU change **{delta:+.1f}%**.")
 table=[]
 for bucket,v in attribution['distance_bins']['20ms'].items():table.append(f"| {bucket} | {v.get('energy',0)} | {v.get('stream1090',0)} | {v.get('all',0)} | {v.get('beyond_recorded_other_DSP',0)} |")
 protected=all(health['before'][k]==health['after'][k] for k in ['pids','configs','methods','workers','samples','gain_db','cap'])
 summary=dict(mac=mac,pi=pi,attribution=attribution,cross_platform_parity=json.loads((a.output/'parity.json').read_text()),protected_health_unchanged=protected,hardware=health['hardware'],production_actions=[],memory_limit_enforced=False,live_backend='executable: pre-existing guard rollback at 2026-11-10 16:37:15 UTC',deployment_recommended=False)
 text=f'''# Incremental native Stream1090: admission and test-relay validation

10 November 2026, Europe/Berlin. **Isolated historical RF replay; nothing deployed.**
Hardware: {health['hardware']}.

The 20 ms decoder now has a test admission bridge and one shared Rust final
transmission history. Energy runs independently in 50 ms blocks. Original stock
arrivals are replayed causally; final output reaches an anonymous RAM-only socket
sink, never a feeder. The original one-second logical reset remains intact.

## Retention and latency

Pi batch extras: **{pi['comparison']['batch_extras']}**; retained with incremental
publication: **{pi['comparison']['retained']}**; losses: **{pi['comparison']['lost']}**;
new transmissions relative to this batch baseline: **{pi['comparison']['incremental_not_in_batch']}**.
Both modes have exact raw native packet/timestamp/order parity and identical raw
energy outputs. Raw native and energy outputs also match exactly between Mac
and Pi; all 79 Pi admitted packet timestamps match the batch condition exactly.
All {pi['results'][0]['stock_records']} captured stock DF17 frames
are byte/order preserved through the sink, with identical stock SHA-256 in both
modes. Other stock frame types were not retained in this fixture.

Latencies below are from the estimated RF packet end to **test-socket receipt**.
They include producer, stock/energy admission and shared deduplication time.
They exclude real live tap scheduling and FR24 processing/network/cloud latency.

| Platform | Native mode | Output | Extras | Early / fallback | Median ms | p95 ms | Max ms | <=250 ms |
|---|---|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

A finalization fallback reuses cached raw rows when early clock/energy evidence is
insufficient; it does not re-decode RF or bypass stock guards. Its slowest packet
is included above. The fixture lacks original 20 ms RF-arrival timestamps. The
+50 ms clock-sensitivity counts are in summary.json; 50 ms is a sensitivity test,
not a proven physical error bound. These are not live antenna-to-feeder results.

## CPU

CPU seconds per RF second; **total is the whole isolated two-method process**,
including admission, stock replay and sink. Worker columns use thread CPU clocks.
Imports, controls and deferred post-measurement references are excluded. This is
not the CPU consumption of the complete live DSP pipeline. There is one paced
run per condition, not a balanced repeated CPU study. The Mac native and energy
worker costs vary substantially between conditions, so its CPU percentage is
sensitive to scheduling/DVFS and must not be treated as a portable overhead.

| Platform | Native mode | Total CPU s/RF s | Native | Energy | Admission main |
|---|---|---:|---:|---:|---:|
{chr(10).join(cpu)}

{chr(10).join(cpu_notes)}

Pi was nice19 on core3 with a quota of 35% of **one** core. A 1 GiB memory limit
was requested, but the host exposes no memory controller; it was **not enforced**.
Measured peak RSS was {pi['peak_RSS_KiB']/1024:.1f} MiB.

The incremental subset needs about **37% of one core** for sustained RF, slightly
more than the imposed 35% quota. Queuing therefore remains: only 19 of 79
extras were under 250 ms on Pi. Zero losses on this short replay does not
establish sustainable real-time throughput. The Mac result must not be
presented as achieved Pi latency.

## Distance and complete recorded-pipeline comparison

The two-method union contains energy plus Stream1090 extras over stock. Some of
these are also recovered by other DSP methods. “Beyond other DSP” removes the
recorded full producer set excluding Stream1090; it must not be added twice to
the complete-pipeline count. There are no new transmissions beyond the recorded
complete pipeline or actual relay in this fixture. This work reduces delay,
not the decoder's recovery threshold.

| Range nm | Energy | Stream1090 | Union | Beyond recorded other DSP |
|---|---:|---:|---:|---:|
{chr(10).join(table)}

Ranges use causal stock positions only, NIC/NACp>=5, age<=15 seconds and no
MLAT/TIS-B. They are not independent truth. The lone >=180 nm packet is inadequate
for a range-performance claim. Six unknown-range packets remain unknown.

The recorded full producer journal has {attribution['recorded_full_producer_events']}
events, including 22 Stream1090 first-winner extras, and the actual relay reference
has {attribution['recorded_relay_frames']} DF17 frames. Other methods' completion
times are absent: this is **not a timed replay of the full current pipeline**.
The eight RF seconds are reserved historical engineering data, not fresh
prospective validation or training labels.

## Controls and live state

Twelve synthetic admission/dedup/socket controls passed on Mac and Pi. The previous
incremental study's boundary, split, deadline, overflow, noise, exact-packet and
sanitizer checks remain applicable: the native incremental decoder was unchanged.
Original-first stock identity/conflict guards, CRC and alignment requirements
were retained. Late stock always passes and its duplicate race is counted.
Protected PIDs/configuration/methods/gain/cap and primary sample-loss counters
unchanged during the completed target run: **{protected}**. No receiver, feeder,
relay or collector restart, routing change, archive deletion or flush occurred.
The RF cap remains 5,000,000,000 bytes.

**Separate pre-existing live event:** the native rollback guard restored the
executable at 16:37:15 UTC, before this admission experiment, after a primary
sample-loss counter increase. The isolated reference is the previously validated
native batch library. The guard trigger does not establish causation. This task
leaves the executable fallback unchanged. FR24 and collection remain connected.

The initial complete Pi prototype lost 13 of the 48 transmissions emitted by
its also-overloaded batch condition; 31 of the 79 deferred-reference extras were
already rejected by that initial batch condition. Cached watermark scanning alone
then retained 74/79. These failed gates are preserved with their exact source
copies. Candidate-specific indexes reduced incremental CPU from 0.6191 to
0.3704 CPU seconds per RF second (about 40%), retaining 79/79. No age threshold,
CRC guard, decoder rule or clock tolerance was relaxed. A separate Mac audit
required the narrowed and original full-index admission functions to return
identical outputs, alignment audits and counters for every slice.

Two setup attempts stopped before RF replay: macOS transfer metadata was treated
as a source filename; then preflight found that the expected live native library
had already been removed by rollback. Both failures are preserved privately.
The completed target runs verify the pinned native baseline and actual
unchanged executable configuration explicitly.

## Next gate

Keep this experimental. First remove remaining Python admission/copy overhead
and reuse the existing production energy frontend instead of duplicating it.
The current result is not a sub-250 ms Pi deployment candidate under this quota.
Before a production admission/publication change, validate on longer untouched
RF with adequate distant opportunities, real tap-arrival timestamps and
all-method completion journals. Review the rollback's sample-loss
event separately before considering another native activation.
'''
 (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(a.output/'report.md').write_text(text);(a.output/'report.html').write_text(render(text))
if __name__=='__main__':main()

"""Sanitized paired-result report. Packet/RF evidence remains private."""
import argparse,json,statistics,importlib.util
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 mac=json.loads((a.private/'mac-view.json').read_text());pi=json.loads((a.private/'pi.json').read_text());health=json.loads((a.private/'pi-health.private.json').read_text());dist=json.loads((a.private/'pi-attribution.json').read_text());parity=json.loads((a.private/'parity.json').read_text());rows=[];cpu=[]
 for name,data in [('Mac',mac),('Pi',pi)]:
  for r in data['results']:
   v=r['metrics']['all'];lat=v['latency'];rows.append(f"| {name} | {r['trial']} | {r['mode']} | {v['emitted']} | {v['early']}/{v['fallback']} | {lat['p50_ms']:.1f} | {lat['p95_ms']:.1f} | {lat['max_ms']:.1f} | {lat['under250']}/{lat['n']} |")
   cpu.append(f"| {name} | {r['trial']} | {r['mode']} | {r['cpu_s_per_RF_s']:.4f} | {r['worker_cpu_s']['native']/8:.4f} | {r['worker_cpu_s']['energy']/8:.4f} | {r['worker_cpu_s']['admission_main']/8:.4f} | {r['consumer_cpu_s_per_RF_s']:.4f} |")
 grouped={m:[r for r in pi['results'] if r['mode']==m] for m in ['legacy','optimized']};avg={m:statistics.mean(r['cpu_s_per_RF_s'] for r in rr) for m,rr in grouped.items()};delta=100*(avg['optimized']/avg['legacy']-1);protected=all(health['before'][k]==health['after'][k] for k in ['pids','configs','methods','workers','samples','gain_db','cap']);table=[]
 for bucket,v in dist['distance_bins']['optimized-trial-1'].items():table.append(f"| {bucket} | {v.get('energy',0)} | {v.get('stream1090',0)} | {v.get('all',0)} | {v.get('beyond_recorded_other_DSP',0)} |")
 source=[]
 for source_name in ['energy','stream1090']:
  for r in grouped['optimized']:
   v=r['metrics'][source_name];lat=v['latency'];source.append(f"| {r['trial']} | {source_name} | {v['emitted']} | {v['early']}/{v['fallback']} | {lat['p50_ms']:.1f} | {lat['p95_ms']:.1f} | {lat['under250']}/{lat['n']} |")
 summary=dict(mac=mac,pi=pi,parity=parity,distance=dist,Pi_average_CPU_s_per_RF_s=avg,Pi_CPU_change_percent=delta,protected_unchanged=protected,production_actions=[],hardware=health['hardware'],memory_enforcement=False,live_native_backend='pre-existing executable fallback unchanged',fresh_RF=False,scope='isolated historical engineering regression, not production feeder latency or full live pipeline replay')
 text=f'''# Four-part Stream1090 latency optimization

10 November 2026, Europe/Berlin. **Implemented by four subagents, integrated and
tested on Mac and {health['hardware']}. Production unchanged.**

The new path shares complete upstream energy candidates, uses persistent Rust
stock/admission indexes, wakes on actual producer completion and retries pending
cold-start slices when new causal evidence arrives. The same 20 ms native decoder,
50 ms energy algorithm, trust resets, CRC/identity/conflict/alignment checks and
shared five-second Rust final transmission history remain in place.

The paired Pi medians improved from 957/571 ms to 189/151 ms, retaining 79/79
transmissions in each trial. **The sub-250 ms tail target is not consistently met:**
optimized p95 was 488 ms and 250 ms, with 52/79 and 75/79 packets under 250 ms.
There is very little margin beneath the 35%-of-one-core quota; supervisor health
monitoring also consumes CPU outside the measured benchmark child. This is a
promising isolated implementation, not a proven production latency guarantee.

## Paired retention and latency

Two trials reverse condition order. Each condition replays the same eight reserved
RF seconds with actual recorded stock arrivals; no future stock or incomplete
producer journal authorizes candidates. Both optimized trials retained the
baseline transmissions: 79/79 retained, zero lost and zero new relative to
that baseline in each trial.

| Host | Trial | Mode | Extras | Early/fallback | Median ms | p95 ms | Max ms | <=250 ms |
|---|---:|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

These are estimated RF-packet-end to **anonymous test-socket receipt** latencies.
Original 20 ms tap-arrival timestamps are missing. They are not measured live
antenna/USB-to-FR24 latency. The +50 ms sensitivity counts remain in summary.json;
50 ms is not a proven bound on clock error. The tiny RF sample is an engineering
regression, not fresh prospective or sustained-load proof.

Optimized Pi publication by method:

| Trial | Source | Extras | Early/fallback | Median ms | p95 ms | <=250 ms |
|---:|---|---:|---:|---:|---:|---:|
{chr(10).join(source)}

## CPU and honest shared-compute accounting

**All upstream energy computation is included once in each measured total.**
The sharing adapter performs no RF decoding; it receives full pre-admission
energy completions from the unchanged test producer. Consumer CPU is total minus
that upstream energy thread's CPU; it is a subtotal, not the complete system cost.
The benchmark does not connect to the live production publisher or measure a
full-system saving from eliminating an actually running duplicate producer.

| Host | Trial | Mode | Total CPU s/RF s | Native | Upstream energy | Admission main | Consumer subtotal |
|---|---:|---|---:|---:|---:|---:|---:|
{chr(10).join(cpu)}

Pi average total: **{avg['legacy']:.4f} -> {avg['optimized']:.4f} CPU seconds per RF second**
(**{delta:+.1f}%**). Admission-main excludes stock-index insertion and other loop
work, which remain included in total. Warmup, import/build/tests and deferred
post-measurement reference replay are excluded. The earlier wrapper microbenchmark
found 54–62% less evaluate CPU and 85–88% less marshalling CPU after bounded
immutable row caching/bulk input copies; those percentages are **not** full-pipeline
CPU reductions. Only two paired trials were run; scheduling/DVFS variation remains.

The job was nice 19/core 3, quota 35% of one core, finite 600 seconds, MemoryMax1G
requested and zero swap. The host exposes no memory controller, so the memory
limit was **not enforced**. Peak measured process RSS: {pi['peak_RSS_KiB']/1024:.1f} MiB.
CPU seconds/RF second describe workload demand, not instantaneous quota usage.

## Distance and complete-pipeline overlap

| Range nm | Energy | Stream1090 | Union beyond stock | Beyond recorded other DSP |
|---|---:|---:|---:|---:|
{chr(10).join(table)}

Ranges use recorded causal stock positions, NIC/NACp>=5, age<=15 seconds, no
MLAT/TIS-B. Unknown stays unknown. There is only one known >=180 nm recovered
packet, inadequate for any range-improvement claim. The 22 transmissions beyond
recorded *other* DSP are existing Stream1090 recovery, not new extras introduced
by this optimization. No new packet appears beyond the recorded complete
pipeline or actual relay. Missing per-method completion times prevent a timed
replay of all current DSP methods; their journals are post-measurement masks only.

## Validation and limits

Native admission passed 333 exact Python/Rust comparisons across 14 control groups,
including 176 historical actual-RF energy/deferred all-source checks. Sharing has 13
controls, completion bridge 22 Python/native controls and cold retry 14 controls.
Tests cover future-evidence rejection, bounds/epochs, CRC/identity/conflicts,
quarter ticks, source priorities, stock eviction, stale cache evidence, idle drains,
pending retries and final fallback. The incremental decoder itself was unchanged;
its earlier boundary/deadline/noise/sanitizer regressions still apply.

Raw native and energy outputs match exactly between Mac and Pi in all trials;
original stock bytes and order are preserved. Detailed parity checks are in
summary.json.
All packet payloads and raw decoder timestamps match. In the admitted Pi output,
10 of 158 paired timestamps differ by one 12 MHz tick (83 ns) because clock
calibration uses earlier causal evidence. The remaining 148 match exactly. All
transmissions remain matched within the unchanged 120 us tolerance.
Original stock DF17 bytes/order are preserved in every condition. The fixture did
not retain all other stock message types. All candidate outputs remain quarantined
and are never training labels or feeder input. No receiver/feeder/relay/collection
service was restarted. Models/gain/routes/switches and the 5,000,000,000-byte RF cap
are unchanged. Protected target state unchanged: **{protected}**.

An initial harness erroneously tested NativeAdmission truthiness by its empty
stock length, selecting the legacy bridge. That Mac result is preserved as
invalid for the optimized condition. An explicit engine/bridge assertion now
prevents this; the setup-only Pi unit was stopped before RF replay, with source
and logs retained. Final results use all four components, including shared input
accounting and completion/retry counters, verified explicitly.

The live native guard had already restored the executable at 16:37 UTC before this
work after a primary sample-loss counter increase. This experiment leaves that
fallback intact; it neither reactivates native inference nor attributes that
older counter event to a particular cause.

## Deployment gate

Nothing was deployed. Judge latency using the actual Pi rows above, not the Mac
result. Before enabling this path, collect longer untouched RF with actual tap
arrival/completion times and adequate distant opportunities, validate sustained
queues/retention against the complete enabled pipeline, and retain the existing
fallback. Component correctness and a short engineering replay do not establish
production latency or range performance.
'''
 spec=importlib.util.spec_from_file_location('previous_report',Path(__file__).resolve().parents[1]/'stream-admission-20261110/report.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(a.output/'report.md').write_text(text);(a.output/'report.html').write_text(module.render(text))
if __name__=='__main__':main()

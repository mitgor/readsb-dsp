"""Render the offline phase-estimator comparison and the safety audit."""
import hashlib,html,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];R=ROOT/'validation/rust-phase-20261029';mac=json.loads((R/'mac.json').read_text());pi=json.loads((R/'pi.json').read_text());health=json.loads((R/'pi-health.json').read_text());assert health['live_unchanged']
lines=['# Disabled soft-phase estimator: C versus Rust','',
'29 October 2026. Offline experiment completed on Mac and Pi; the working Rust coherent pipeline, FR24, ADS-B Exchange and RF collection remain unchanged. This estimator remains disabled.','',
'## Why this routine?','',
'The historical 72-capture Pi 4 comparison attributed a mean 0.719 CPU seconds per approximately one RF second to the soft-phase decision stage, including coherent preparation. The coherent kernel itself averaged 0.071; sequence work 0.167; shared frontend 0.275. This makes the disabled soft-phase/EM estimator a useful next native-heavy target. Larger header/CFAR/legacy-joint whole-method totals include substantial Python/NumPy work and cannot rank maintained C functions. This is not an exhaustive proof of a globally most expensive C function. [Selection evidence](selection.json).','',
'The port targets sf_em / method=0 of research_science.c: soft PPM probabilities, payload-assisted gain, five-frequency refinement per iteration, final bit confidence and restricted CRC repair. Initial coherent logits/confidence and carrier seeds are frozen into the same input for both versions; their preparation is excluded. Rust implements the estimator itself and reuses the validated Rust CRC/quantile helpers. It makes no C DSP-decoder calls. The original sequence and combined science methods are outside scope.','',
'## Matched CPU results','',
'Nine fresh-process trials, alternating implementation order, identical preallocated driver/buffers, two untimed warmups. Lower time is better. Compilation, initialization and I/O are excluded.','',
'| Target | Iterations | C µs/window | Rust µs/window | CPU saving |',
'|---|---:|---:|---:|---:|']
for target,x in [('Mac M4 Max',mac),('Raspberry Pi 5',pi)]:
 for count,d in x['iterations'].items():lines.append(f"| {target} | {count} | {d['summary']['c']['cpu_us_per_window']:.3f} | {d['summary']['rust']['cpu_us_per_window']:.3f} | {d['cpu_saving_percent']:.1f}% |")
lines+=['',
'The two-iteration row matches the historical candidate setting. One and four iterations exercise its bounded range. Historical Pi 4 stage costs and current Pi 5 kernel timings use different hardware/scopes and must not be treated as direct speedup measurements. None of these kernel savings are whole-pipeline or wattage claims.','',
'## Memory and parity','',
'| Target, two iterations | Implementation | Resident MiB | Debug-stripped executable KiB |',
'|---|---|---:|---:|']
for target,x in [('Mac',mac),('Pi',pi)]:
 for name in ['c','rust']:
  s=x['iterations']['2']['summary'][name];lines.append(f"| {target} | {name} | {s['resident_bytes']/1048576:.3f} | {x['size_audit'][name]['debug_stripped_bytes']/1024:.1f} |")
lines+=['',
'Resident memory is the complete standalone process, including identical input/output buffers; compiler memory is excluded. Linux uses exec-local VmHWM/current RSS, not inherited launcher ru_maxrss. Executable size is measured on uniformly debug-stripped copies, separate from timed executables and physical RAM. Rust statically includes parts of its standard runtime.','',
'The fixture contains 368 windows drawn from 42 already consumed RF captures plus deterministic noise, with identical precomputed initial decisions and a mixture of supplied/automatic carrier seeds. All packet bytes, repair choices and hard decisions match. Floating diagnostics use rtol=1e-12 and atol=1e-12; bitwise equality is also checked and reported below.','']
for target,x in [('Mac',mac),('Pi',pi)]:
 for count,d in x['iterations'].items():
  p=d['parity'];lines.append(f"{target}, {count} iterations: all output bytes identical = {p['exact_all_arrays']}; maximum logit difference {p['logits_max_abs']:.3g}, confidence {p['confidence_max_abs']:.3g}, frequency {p['frequency_max_abs']:.3g} Hz. Accepted window outputs: {d['summary']['c']['valid_window_outputs']}; Gaussian-control accepts: {p['noise_valid']}.")
lines+=['',
'For each iteration setting, separate synthetic controls recover all 48 clean packets and 16 weak repair cases (eight one-bit, eight two-bit), with the expected CRC-valid payload and matching repairs. All 64 Gaussian negatives are rejected. The 32 field-fixture noise controls are also rejected. These finite controls do not establish a general false-positive bound. No unverified prediction is promoted into a training label or feeder input; no new reception improvement is claimed.','',
'Rust 1.99.1 opt-level 3, one codegen unit, panic=abort; C -O3 -std=c11 -ffp-contract=off. No fast-math or target-native specialization. Elementary sine/cosine/exp/min/max use target math semantics. C and Rust retain their typed median-sort library choices, and different compiler backends remain a confounder; this is not proof of an intrinsic language advantage.','',
'## Isolation and interrupted first run','',
'The first Pi run was stopped by the safety supervisor after the DSP service was restarted outside this experiment. Its optional latency metric was temporarily None during startup, causing the monitor to reject the sample. Partial timings are excluded. FR24, readsb and RF capture stayed running; the existing Rust coherent release remained active. The event is preserved in [interruption evidence](interruption.json) and the original log.','',
'The monitor was clarified to detect PID changes before inspecting optional startup metrics. The same frozen estimator and input were then rerun against a fresh healthy baseline. The successful second attempt preserves all protected receiver, feeder, capture and shadow PIDs and configurations, with unchanged SDR loss/drop counters. The test supervisor samples every three seconds and kills only its own test process group if health checks repeatedly fail.','',
'All Pi work uses owned tmpfs, nice 19, core 3, 35% CPU quota, bounded memory and runtime. Rust compiler archives are checksum-verified and temporary; no packages, libraries, models, gains, method switches, services, routing or capture caps were changed by the experiment. No live SDR or mirror consumer was opened, and no extra capture flush occurred.','',
'## Decision and reproduce','',
'Keep the estimator disabled. The Rust implementation is a performance candidate, not an instruction to deploy an expensive research method. Earlier evidence for useful incremental distant recoveries remains sparse; reducing its cost does not establish a reception benefit.','',
'[Source and reproduction](../../experiments/rust-phase/README.md) · [Rust estimator](../../experiments/rust-phase/phase.rs) · [Mac trials](mac.json) · [Pi trials](pi.json) · [Pi controls](pi-controls.json) · [Mac controls](mac-controls.json) · [Receiver health](pi-health.json) · [Manifest](input-manifest.json) · [Provenance](provenance.json).','']
(R/'report.md').write_text('\n'.join(lines));parts=[];table=False
for line in lines:
 if line.startswith('|'):
  cells=[x.strip() for x in line.strip('|').split('|')]
  if not table:parts.append('<table>');table=True
  if all(re.fullmatch(r'[-:]+',x) for x in cells):continue
  parts.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>');continue
 if table:parts.append('</table>');table=False
 s=html.escape(line);s=re.sub(r'\[([^]]+)\]\(([^)]+)\)',lambda m:'<a href="'+(m[2].replace('../../','https://github.com/mitgor/readsb-dsp/blob/codex/rust-phase-benchmark/') if m[2].startswith('../../') else m[2])+'">'+m[1]+'</a>',s)
 if line.startswith('# '):parts.append('<h1>'+s[2:]+'</h1>')
 elif line.startswith('## '):parts.append('<h2>'+s[3:]+'</h2>')
 elif line:parts.append('<p>'+s+'</p>')
(R/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Offline soft-phase estimator C versus Rust</title><style>body{max-width:1150px;margin:32px auto;padding:0 20px;background:#101b2a;color:#e3edf8;font:16px/1.6 system-ui}table{border-collapse:collapse;width:100%}td{padding:9px;border-bottom:1px solid #456}a{color:#8dc4ff}</style>'+''.join(parts))

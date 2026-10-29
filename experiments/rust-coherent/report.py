"""Render the six-way controlled comparison without RF/payload content."""
import html,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];R=ROOT/'validation/rust-coherent-20261029'
mac=json.loads((R/'mac.json').read_text());pi=json.loads((R/'pi.json').read_text());sizes={name:json.loads((R/(name+'-size.json')).read_text()) for name in ['mac','pi']};health=json.loads((R/'health-check.json').read_text());assert health['unchanged']
for x in [mac,pi]:assert 'rustc 1.99.1' in x['toolchains']['rustc'] and x['windows']==3269 and x['trials']==9
names={'c-old':'Original C','c-current':'Current optimized C','goose':'Goose','rust':'Rust / standard sort','rust-libc':'Rust / libc-sort control','rust-matched':'Rust / matched-sort control'}
lines=['# Coherent decoder: C, Rust and Goose, one-to-one','',
'Completed 29 October 2026. The working receiver pipeline remains unchanged.','',
'## CPU comparison','',
'All six variants were rebuilt and rerun together on exactly the same 3,269 saved windows. These are nine-trial median process CPU times per presented window; initialization, file I/O and compilation are excluded. Lower time is better. Negative savings mean a slowdown.','',
'| Target | Implementation | µs/window | Saving vs original C | Saving vs current C |',
'|---|---|---:|---:|---:|']
for target,d in [('Mac M4 Max',mac),('Raspberry Pi 5',pi)]:
 for name in ['c-old','rust','goose','c-current','rust-libc','rust-matched']:
  s=d['summary'][name];lines.append(f"| {target} | {names[name]} | {s['median_cpu_us_per_window']:.3f} | {s['cpu_saving_vs_old_c_percent']:.1f}% | {s['cpu_saving_vs_current_c_percent']:.1f}% |")
lines+=['','## Memory and code size','',
'Whole standalone-process resident memory includes identical preallocated input/output buffers, tables and library/runtime pages. Virtual address reservation is not physical RAM. Executable size is disk code size, not resident RAM.','',
'| Target | Implementation | Resident MiB | Extra virtual MiB vs original C | Executable KiB, debug stripped |',
'|---|---|---:|---:|---:|']
for target,d in [('Mac',mac),('Pi',pi)]:
 for name in ['c-old','c-current','goose','rust','rust-libc','rust-matched']:
  s=d['summary'][name];delta=s['virtual_bytes']-d['summary']['c-old']['virtual_bytes'];lines.append(f"| {target} | {names[name]} | {s['resident_bytes']/1048576:.3f} | {delta/1048576:.2f} | {sizes['mac' if target=='Mac' else 'pi']['variants'][name]['debug_stripped_bytes']/1024:.1f} |")
lines+=['','Goose reserves roughly 4 GiB extra virtual address space for runtime stacks, mostly untouched. Rust has a larger executable because it includes parts of its standard runtime; code size and resident memory are shown separately. The table uses uniformly debug-stripped copies: prebuilt Rust standard-library debug sections survived staticlib compilation on Pi. Raw and stripped sizes/hashes are in mac-size.json and pi-size.json; the original binaries used for CPU/RSS were not modified. The several-megabyte sample buffers dominate this standalone RSS. Linux memory uses exec-local VmHWM/current RSS rather than launcher-inherited ru_maxrss; Mac uses Mach RSS/getrusage.','',
'## What is actually one-to-one?','',
'Every variant implements the ordinary 41-bin coherent decoder: the same preamble carrier search, phase unwrap, magnitude quantiles, weighted/refined phase fit, coherent bit scores, protected weak-bit selection and CRC repair. There are no changed DSP thresholds, no new retry hypotheses and no reduced-accuracy fast path. Common elementary libm operations preserve numerical comparability. The Rust port performs the full decoder computation itself and never calls a C decoder.','',
'The common C input/output harness gives every implementation identical IQ bytes, order, batch size, preallocated output buffers and warmups. Safe Rust indexing checks remain in its hot loops. Rust FFI/raw-pointer conversion is confined to the ABI boundary and elementary math; the libc sorting control explicitly calls libc qsort. Goose standard bounds checks remain enabled.','',
'The default sort differs by implementation: original C uses libc qsort; Goose uses its specialized typed standard sort; current C uses the Goose-derived C sort; Rust uses std sort_unstable_by. Therefore two diagnostic Rust variants are included: Rust-libc uses the same libc sort as original C, and Rust-matched ports the same typed-sort algorithm as current C/Goose. These controls distinguish sorting-library choices from the rest of the decoder.','',
'## Interpreting the controls','']
for target,d in [('Mac',mac),('Pi',pi)]:
 s=d['summary'];lines.append(f"On {target}, Rust with its standard sort saves {s['rust']['cpu_saving_vs_current_c_percent']:.1f}% versus current C; the matched-sort Rust control saves {s['rust-matched']['cpu_saving_vs_current_c_percent']:.1f}% versus current C. Rust-libc saves {s['rust-libc']['cpu_saving_vs_old_c_percent']:.1f}% versus original C. These measurements suggest how much comes from library selection, but do not establish an intrinsic language-speed advantage.")
lines+=['',
'Rust 1.99.1 is used on both systems, compiled at opt-level 3 with one codegen unit, panic=abort and no debug info. Goose v2026.3 emits standalone C. Original/current C and generated Goose C use the same target compiler with -O3 -std=c11 -ffp-contract=off. No variant enables fast-math or target-native specialization. Mac uses Apple Clang; Pi uses GCC; Rust uses its bundled LLVM. Compiler/backend differences remain a confounder, even with matching algorithm controls.','',
'## Parity and limits','',
'All six versions produced the same 262 CRC-valid window outputs and 2,582 tracked windows. Packet bytes, repairs, inlier counts, tracked/valid flags and hard-bit decisions match exactly, and all 32 deterministic noise controls are rejected. Floating diagnostics meet the declared rtol=1e-12, atol=1e-15 tolerance; maximum differences are retained in each JSON.','']
for target,d in [('Mac',mac),('Pi',pi)]:
 for name in ['rust','goose']:
  c=d['parity'][name];lines.append(f"{target}, {names[name]}: largest absolute logit difference {c['logits_max_abs']:.3g}; confidence {c['confidence_max_abs']:.3g}; carrier frequency {c['frequency_max_abs']:.3g} Hz.")
lines+=['',
'The Rust tests check a known CRC packet, initialization and invalid bounds. The matched sort also passes 200,000 ordered/reversed/duplicate/adversarial/random arrays. This is bounded implementation regression, not a new false-positive certification or a count of unique extra aircraft transmissions. The 42 RF files are previously consumed development captures; no new or reserved prospective RF was used.','',
'No whole-pipeline CPU saving, wattage reduction or improvement in reception is claimed. This test times only ordinary coherent-window decoding; acquisition, shared FIR, pair retry, neural work and feeder transport are excluded. A working-pipeline change would need its own validation and deployment request.','',
'## Receiver isolation','',
'The Pi identifies as Raspberry Pi 5 Model B, not Pi 4. The official checksum-verified Rust compiler and standard library were extracted only into the owned tmpfs experiment tree. No system package installation occurred. Build and tests ran under nice 19, core 3, CPUQuota 35%, MemoryMax 1536 MiB and bounded runtime. Compiler memory is excluded from decoder measurements; elapsed time under quota is not a throughput measure.','',
'Protected decoder, DSP, FR24, ADS-B Exchange, relay and capture PIDs, config hashes, gain and method switches match before/after. Sample-loss/drop counters did not increase. No services were restarted, no routing/model/capture settings changed, and no live SDR or mirror input was opened.','',
'## Artifacts and reproduction','',
'[Experiment source and instructions](../../experiments/rust-coherent/README.md) · [Rust decoder](../../experiments/rust-coherent/coherent.rs) · [Mac trials](mac.json) · [Pi trials](pi.json) · [Provenance](provenance.json) · [Receiver health](health-check.json) · [Input manifest](input-manifest.json). Private RF, generated binaries and temporary compiler files are excluded from Git.','']
(R/'report.md').write_text('\n'.join(lines))
parts=[];table=False
for line in lines:
 if line.startswith('|'):
  cells=[x.strip() for x in line.strip('|').split('|')]
  if not table:parts.append('<table>');table=True
  if all(re.fullmatch(r'[-:]+',x) for x in cells):continue
  parts.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>');continue
 if table:parts.append('</table>');table=False
 s=html.escape(line);s=re.sub(r'\[([^]]+)\]\(([^)]+)\)',lambda m:'<a href="'+(m[2].replace('../../','https://github.com/mitgor/readsb-dsp/blob/codex/rust-coherent-comparison/') if m[2].startswith('../../') else m[2])+'">'+m[1]+'</a>',s)
 if line.startswith('# '):parts.append('<h1>'+s[2:]+'</h1>')
 elif line.startswith('## '):parts.append('<h2>'+s[3:]+'</h2>')
 elif line:parts.append('<p>'+s+'</p>')
(R/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>C versus Rust versus Goose coherent decoder</title><style>body{max-width:1200px;margin:32px auto;padding:0 20px;background:#101b2a;color:#e3edf8;font:16px/1.6 system-ui}table{border-collapse:collapse;width:100%}td{padding:9px;border-bottom:1px solid #456}a{color:#8dc4ff}</style>'+''.join(parts))

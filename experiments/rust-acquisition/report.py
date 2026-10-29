"""Generate scorer/selector parity, performance and receiver-isolation report."""
import html,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];R=ROOT/'validation/rust-acquisition-20261029';mac=json.loads((R/'mac.json').read_text());pi=json.loads((R/'pi.json').read_text());h=json.loads((R/'pi-health.json').read_text());assert h['live_unchanged'];packets=json.loads((R/'pi-packets.json').read_text())
lines=['# Improved acquisition: C versus Rust','',
'29 October 2026. The scorer and bounded candidate selector have an offline Rust port. Live acquisition remains disabled. No working decoder, feeder, collector, model, gain, routing or method setting was changed by this experiment.','',
'## Selection and scope','',
'The historical bundle comparison attributed roughly 0.120 CPU seconds per RF second to selection in the current bundle and 0.437 with acquisition enabled, an increase of about 0.317. This identifies native-heavy acquisition scoring/selection as a useful next target after coherent and soft-phase ports. Aggregate legacy-bundle timings do not identify a single most expensive function; this is the best-supported next maintained C target, not an exhaustive global profile. [Historical selection evidence](selection.json).','',
'The C reference is the maintained NEON-optimized pipeline_extended_neon.c, not an intentionally slow old implementation. Rust mirrors its four-lane double accumulation order, rolling normalization, threshold, plateau handling, peak spacing, ranked top-k, strict halo/core bounds, and -2 equal-score fallback. It uses standard sorting/vector allocation and explicit bounded NEON loads. Compiler/backend/library differences remain part of the result.','',
'## Matched CPU comparison','',
'Nine fresh-process alternating-order trials on identical frozen inputs. Lower time is better. Positive saving means Rust is faster; negative means slower. CPU is process time per input power sample, not quota-limited elapsed time.','',
'| Target | Routine / budget | C ns/sample | Rust ns/sample | Rust CPU saving |',
'|---|---|---:|---:|---:|']
for target,d in [('Mac M4 Max',mac),('Raspberry Pi 5',pi)]:
 for name,v in d['scenarios'].items():lines.append(f"| {target} | {name} | {v['summary']['c']['cpu_ns_per_power_sample']:.3f} | {v['summary']['rust']['cpu_ns_per_power_sample']:.3f} | {v['cpu_saving_percent']:.1f}% |")
lines+=['',
'The current historical acquisition budget is 16. On Pi, Rust improves the default selector by about 12.4%, while on Mac the same port is about 8.1% slower. This platform difference is why target measurements matter; it is not proof of an intrinsic Rust advantage. No whole-pipeline or wattage reduction is claimed, and acquisition is currently disabled.','',
'## Process memory','',
'| Target / full selector budget 16 | C resident MiB | Rust resident MiB |',
'|---|---:|---:|']
for target,d in [('Mac',mac),('Pi',pi)]:
 v=d['scenarios']['selector-16']['summary'];lines.append(f"| {target} | {v['c']['resident_bytes']/1048576:.3f} | {v['rust']['resident_bytes']/1048576:.3f} |")
lines+=['',
'RSS includes the common fixture buffers, library/runtime and each implementation’s allocator footprint. The scorer-only case also preallocates full score arrays, so its process memory must not be compared directly to selector-only RSS. Rust uses fallible vector reservations and standard unstable sorting; C uses malloc/calloc and qsort. Allocations inside the selector are timed; caller buffers, loading, initialization, compilation and output I/O are excluded.','',
'## Score, candidate and packet parity','',
'The 24 time-spread saved blocks contain 3,979,973 power samples, about 0.991 recorded RF seconds, from previously consumed development captures. Both versions receive identical power, exact frozen float-derived template weights, core bounds and candidate budgets. Full score arrays and complete candidate IDs/order/scores match byte-for-byte in every measured scenario. No new or reserved prospective RF was consumed.','',
'Additional controls pass 1,201 exact scorer/selector cases, budgets 1/8/16/64/256, tail and small lengths, zero/flat power, plateau/distance behavior, unchanged inputs, invalid-argument checks, and the -2 tie fallback. Across 64 Gaussian I/Q blocks, acquisition emits hypotheses; none becomes CRC-valid through the frozen installed coherent decoder. A hypothesis is not a recovered packet. This finite set is not a false-alarm certification.','',
'Paired original I/Q was reconstructed and checksum-verified against frozen power. Both selectors feed the same read-only frozen coherent decoder in the offline process. Candidate arrays and every downstream decoder array match exactly. Mac and Pi have identical packet/start/repair signatures:','',
'| Budget | Candidate windows | CRC-valid window outputs | Repaired window outputs |',
'|---:|---:|---:|---:|']
for budget,v in packets['budgets'].items():lines.append(f"| {budget} | {v['candidates']} | {v['crc_valid_window_outputs']} | {v['repaired_window_outputs']} |")
lines+=['',
'These are raw CRC-valid window outputs, not unique transmissions or incremental recoveries beyond stock/current DSP. Duplicate payload/time and stock-address admission remain outside this experiment. No prediction was forwarded or used as a training label.','',
'## Isolation and current receiver health','',
'The timed Pi run preserves all monitored service PIDs, shadow PID, protected configuration hashes, gain/method selections and SDR loss/drop counters. It runs in owned tmpfs at nice 19, core 3, 35% CPU quota, bounded memory/runtime. A health supervisor polls every three seconds and can terminate only its owned test process group. No system packages or Rust toolchain were installed; the temporary compiler archives were checksum-verified. The downstream packet check uses a separate bounded read-only replay, never live SDR or mirror input.','',
'After the timed benchmark ended at 21:10:39 UTC, the DSP service was externally restarted at 21:12:34 UTC. The experiment did not request that restart; timing results were already closed. Final checks confirm receiver/feeder/capture PIDs and configurations unchanged, the existing Rust coherent release active, its watchdog healthy and SDR sample-loss/drop counters zero. The separate event is recorded in [final health](final-health.json) and [restart journal](post-benchmark-external-restart.txt).','',
'## Decision and artifacts','',
'Keep this port offline and acquisition disabled as requested. Target CPU is promising, but a faster disabled method alone is not a demonstrated reception benefit or permission to change the working pipeline.','',
'[Source and reproduction](../../experiments/rust-acquisition/README.md) · [Rust port](../../experiments/rust-acquisition/acquisition.rs) · [Mac trials](mac.json) · [Pi trials](pi.json) · [Pi controls](pi-controls.json) · [Packet parity](pi-packets.json) · [Monitored health](pi-health.json) · [Provenance](provenance.json).','']
(R/'report.md').write_text('\n'.join(lines));parts=[];table=False
for line in lines:
 if line.startswith('|'):
  cells=[x.strip() for x in line.strip('|').split('|')]
  if not table:parts.append('<table>');table=True
  if all(re.fullmatch(r'[-:]+',x) for x in cells):continue
  parts.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>');continue
 if table:parts.append('</table>');table=False
 s=html.escape(line);s=re.sub(r'\[([^]]+)\]\(([^)]+)\)',lambda m:'<a href="'+(m[2].replace('../../','https://github.com/mitgor/readsb-dsp/blob/codex/rust-acquisition-benchmark/') if m[2].startswith('../../') else m[2])+'">'+m[1]+'</a>',s)
 if line.startswith('# '):parts.append('<h1>'+s[2:]+'</h1>')
 elif line.startswith('## '):parts.append('<h2>'+s[3:]+'</h2>')
 elif line:parts.append('<p>'+s+'</p>')
(R/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Offline acquisition C versus Rust</title><style>body{max-width:1150px;margin:32px auto;padding:0 20px;background:#101b2a;color:#e3edf8;font:16px/1.6 system-ui}table{border-collapse:collapse;width:100%}td{padding:9px;border-bottom:1px solid #456}a{color:#8dc4ff}</style>'+''.join(parts))

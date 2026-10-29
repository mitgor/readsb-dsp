"""Generate the Rust live rollout report from saved verification artifacts."""
import hashlib,html,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];R=ROOT/'validation/rust-live-20261029'
pi=json.loads((R/'pi.json').read_text());mac=json.loads((R/'mac.json').read_text());d=json.loads((R/'deployment.json').read_text());capture=json.loads((R/'capture-after.json').read_text());guard=json.loads((R/'guard-status.json').read_text());assert d['activated'] and guard['release']['state']=='active' and guard['guard']['state']=='healthy'
a=d['samples'][0];b=d['samples'][-1];before=d['before']
lines=['# Rust coherent decoding is live','',
'Activated on 29 October 2026, with persistent automatic rollback to the previous optimized C libraries. Ordinary and pair-lag retry kernels use Rust; the existing C peak-selection helper and the rest of the DSP/neural pipeline retain their existing implementations.','',
'## Release validation','',
'| Target | Branch | Optimized C µs/window | Release Rust µs/window | Kernel CPU saving |',
'|---|---|---:|---:|---:|']
for target,x in [('Mac M4 Max',mac),('Raspberry Pi 5',pi)]:
 for mode,name in [('base','ordinary'),('pair','pair-lag retry')]:
  v=x['branches'][mode];lines.append(f"| {target} | {name} | {v['cpu_us_per_window']['reference']:.3f} | {v['cpu_us_per_window']['rust']:.3f} | {v['cpu_saving_percent']:.1f}% |")
lines+=['',
'Each release branch was compared against its actual installed C library with the same C ABI/dlopen driver and seven trials. The release includes safe Rust indexing, the nonfinite quantile fallback, the existing C peak selector and the production shared-library ABI. No fast-math or relaxed packet checks are enabled.','',
'On Pi every output array matches bit-for-bit across 3,269 recorded windows, including floating diagnostics. Each branch also passes 8,192 augmented phase/amplitude windows with unchanged packets/repairs/hard decisions, 500 exact peak-selector cases and ABI guard checks. Thirty-two noise controls remain rejected. On Mac tiny floating confidence differences required a 1e-12 absolute diagnostic tolerance; packet bytes, repairs and hard decisions remain exact. Initial tighter Mac diagnostic assertions and their cause are documented in the experiment guide.','',
'Both Rust branch unit tests pass, all 41 integration tests pass with Rust libraries built into the checkout, and seven watchdog/rollback fault-injection tests pass. Saved RF is already consumed development data. This is implementation regression, not fresh reception validation or a claim of more packets. Kernel CPU savings do not equal whole-system savings.','',
'## Live observation','',
f"The activation processed {b['aligned_seconds']-a['aligned_seconds']} aligned RF seconds during {b['unix']-a['unix']:.1f} seconds of observation and forwarded {b['feed']['counts']['relayed_coherent']-a['feed']['counts']['relayed_coherent']:,} coherent packets. Readsb, FR24, the combined relay, ADS-B Exchange and RF capture retain their original PIDs. Both coherent workers map the installed Rust library inodes; backend markers identify ordinary and pair builds.",'',
'Only shadow/DSP workers restarted. Stock feeding continued during the brief rescue pause. All gain, method, worker-affinity and protected configuration checks passed; receiver sample-loss/drop counters stayed at zero. FR24 remained connected with recent uploads. Neither neural model nor acceptance/routing logic changed.','',
f"RF capture remains enabled with PID {capture['pid']}, no current capture error, and the existing {capture['disk_limit_bytes']/1e9:.0f} GB cap ({capture['disk_limit_bytes']:,} bytes). It was not stopped or forcibly flushed. Bounded RAM sampling and scheduled saves retain their prior behavior. Graceful shadow shutdown preserved its separate CRC research cache; archive bytes changed from {before['crc_archive']['disk_bytes']:,} to {b['crc_archive']['disk_bytes']:,}. No historical archive was removed.",'',
'## Automatic rollback','',
'The enabled guard checks every 15 seconds and restores the previous optimized C libraries after three consecutive unhealthy checks. It checks freshness, processing/stock progress, worker health, uploads, loss counters, repeated restarts and installed mappings/hashes. Normal startup gets a grace period. Activation has its own 120-second observation and rollback, plus a systemd failure handler. Guard status is stored in RAM; persistent state is written for release/rollback transitions.','',
'Rollback restarts only adsb-rescue-shadow. It preserves readsb, feeders, relay, capture, gain, models, switches and caps. Rust is not automatically re-enabled after a rollback. This is an operational health guard, not an automatic RF accuracy oracle.','',
'```sh','sudo /usr/local/sbin/adsb-coherent-rust-mode status','sudo /usr/local/sbin/adsb-coherent-rust-mode rollback','```','',
'## Sources and evidence','',
'[Production Rust](../../src/rescue/coherent_rust.rs) · [Build and deployment guide](../../experiments/rust-live/README.md) · [Pi release test](pi.json) · [Mac test](mac.json) · [Deployment](deployment.json) · [Guard status](guard-status.json) · [Capture status](capture-after.json) · [Rollback tests](guard-tests.txt) · [Integration tests](integration-tests.txt).','']
(R/'report.md').write_text('\n'.join(lines));parts=[];table=False;code=False
for line in lines:
 if line.startswith('```'):parts.append('</code></pre>' if code else '<pre><code>');code=not code;continue
 if code:parts.append(html.escape(line)+'\n');continue
 if line.startswith('|'):
  cells=[x.strip() for x in line.strip('|').split('|')]
  if not table:parts.append('<table>');table=True
  if all(re.fullmatch(r'[-:]+',x) for x in cells):continue
  parts.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>');continue
 if table:parts.append('</table>');table=False
 s=html.escape(line);s=re.sub(r'\[([^]]+)\]\(([^)]+)\)',lambda m:'<a href="'+(m[2].replace('../../','https://github.com/mitgor/readsb-dsp/blob/codex/rust-coherent-live/') if m[2].startswith('../../') else m[2])+'">'+m[1]+'</a>',s)
 if line.startswith('# '):parts.append('<h1>'+s[2:]+'</h1>')
 elif line.startswith('## '):parts.append('<h2>'+s[3:]+'</h2>')
 elif line:parts.append('<p>'+s+'</p>')
(R/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Rust coherent active with automatic C rollback</title><style>body{max-width:1100px;margin:32px auto;padding:0 20px;background:#101b2a;color:#e3edf8;font:16px/1.6 system-ui}table{border-collapse:collapse;width:100%}td{padding:9px;border-bottom:1px solid #456}a{color:#8dc4ff}pre{white-space:pre-wrap}</style>'+''.join(parts))
source_files=['src/rescue/coherent_rust.rs','src/rescue/coherent_peaks.c','tools/build_coherent_rust.py','tools/rust_coherent_mode.py','experiments/rust-live/validate.py']
(R/'provenance.json').write_text(json.dumps({'sources_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_files},'proof_sha256':hashlib.sha256((R/'pi.json').read_bytes()).hexdigest(),'deployment_sha256':hashlib.sha256((R/'deployment.json').read_bytes()).hexdigest(),'live_backend':'rust ordinary and pair-lag','capture_unchanged':True,'automatic_rollback_enabled':True},indent=2)+'\n')

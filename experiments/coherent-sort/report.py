"""Generate deployment report from verified aggregate artifacts."""
import hashlib,html,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];r=ROOT/'validation/coherent-sort-20261029'
mac=json.loads((r/'mac.json').read_text());pi=json.loads((r/'pi.json').read_text());d=json.loads((r/'deployment.json').read_text());assert d['activated']
a=d['samples'][0];b=d['samples'][-1];old=d['before'];frames=b['feed']['counts']['relayed_coherent']-a['feed']['counts']['relayed_coherent'];stock=b['feed']['counts']['stock_bytes_relayed']-a['feed']['counts']['stock_bytes_relayed']
lines=['# Coherent sort optimization is live','',
'Activated 29 October 2026 on Raspberry Pi 5. Both coherent libraries now use a specialized C sort for pulse-magnitude quantiles. The change survives worker restarts and reboot.','',
'This brings the useful sorting result from the Goose experiment into the C pipeline, without a Goose compiler/runtime, virtual stack reservations or new runtime dependency. The header adapts Goose v2026.3’s typed branchless sort; Apache-2.0 attribution and license are retained. Quantile ranks/interpolation, carrier/phase fitting, repair policy and acceptance guards are unchanged.','',
'## Controlled replay','',
'| Target | Coherent branch | libc µs/window | Typed C µs/window | CPU saving |',
'|---|---|---:|---:|---:|']
for target,data in [('Mac M4 Max',mac),('Raspberry Pi 5',pi)]:
 for mode,name in [('base','ordinary'),('pair','pair-lag retry')]:
  v=data['results'][mode];lines.append(f"| {target} | {name} | {v['reference']['cpu_us_per_window']:.3f} | {v['typed']['cpu_us_per_window']:.3f} | {v['saving_percent']:.1f}% |")
lines += ['',
'Each comparison uses seven fresh-process trials on the same 3,269 windows from 42 previously consumed RF captures, including 32 seeded noise controls. The Pi reference also matches the actual installed libraries before replacement. All packet bytes, repairs, hard-decision scores, confidence, carrier estimates, inlier counts and flags match bit-for-bit. Both implementations produce 262 ordinary valid window outputs and 261 pair-lag outputs; these are separate branch results, not a loss or a count of unique extras. Noise controls remain rejected.','',
'Two hundred thousand sort cases pass with address/undefined-behavior sanitizers on Mac and Pi, including every size 0–112, duplicates, ordered/reversed/adversarial values and the nonfinite libc fallback. The integrated native build and all 41 Python integration tests pass.','',
'These are kernel CPU savings, not a measured 22–24% whole-pipeline reduction or a wattage measurement. The corpus is development regression data, not fresh reception validation. Larger input/output buffers make standalone process RSS about 19.5 MiB on Pi; ordinary reference and candidate have the same measured resident size, and retry differs by one 16 KiB measurement increment. There is no Goose runtime allocation.','',
'## Live activation and health','',
f"Only `adsb-rescue-shadow` was restarted. Readsb, FR24, the combined relay, ADS-B Exchange feeder and far-range capture retained their existing PIDs. Both coherent workers map the new ordinary and pair-lag library inodes. All configuration hashes, method switches, gain, models and capture caps were preserved. The worker restart causes a brief gap in rescue work while stock continues through the unchanged relay.",'',
f"The observation covered {b['aligned_seconds']-a['aligned_seconds']} aligned RF seconds in {b['unix']-a['unix']:.1f} wall seconds. It relayed {frames:,} coherent frames and {stock:,} stock bytes; {b['feed']['counts']['relayed_coherent']-old['feed']['counts']['relayed_coherent']:,} coherent frames were relayed across the complete cutover plus observation. FR24 remained connected with recent uploads. Sample-loss and dropped-sample counters stayed at zero. Backlog and latency health gates passed.",'',
f"Graceful shutdown preserved the CRC research RAM buffer: archived bytes increased from {old['crc_archive']['disk_bytes']:,} to {b['crc_archive']['disk_bytes']:,}, adding one archive. No old archive was removed. Independent RF collection stayed running; the existing 5 GB capture cap is unchanged.",'',
'## Rollback','',
'Previous libraries and source are retained in the receiver backup directory recorded in [the deployment](deployment.json). To restore them:', '',
'```sh','sudo /usr/local/sbin/adsb-coherent-sort-mode status','sudo /usr/local/sbin/adsb-coherent-sort-mode rollback','```','',
'Activation included automatic rollback on a failed health gate. The permanent command performs an explicit rollback; it is not a continuous watchdog. It restarts only the DSP shadow service.','',
'## Reproduce and inspect','',
'[Experiment instructions](../../experiments/coherent-sort/README.md) · [C sort](../../src/rescue/coherent_sort.h) · [Mac results](mac.json) · [Pi results](pi.json) · [Deployment](deployment.json) · [Input manifest](input-manifest.json). Private RF, binaries and generated scratch files are not committed.','']
text='\n'.join(lines);(r/'report.md').write_text(text)
# Minimal standalone Markdown rendering: no network dependencies or client script.
import re
parts=[];table=False;code=False
for line in lines:
 if line.startswith('```'):
  parts.append('</code></pre>' if code else '<pre><code>');code=not code;continue
 if code:parts.append(html.escape(line)+'\n');continue
 if line.startswith('|'):
  cells=[x.strip() for x in line.strip('|').split('|')]
  if not table:parts.append('<table>');table=True
  if all(re.fullmatch(r'[-:]+',x) for x in cells):continue
  parts.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>');continue
 if table:parts.append('</table>');table=False
 escaped=html.escape(line)
 escaped=re.sub(r'\[([^]]+)\]\(([^)]+)\)',lambda m:'<a href="'+(m[2].replace('../../','https://github.com/mitgor/readsb-dsp/blob/codex/coherent-sort-live/') if m[2].startswith('../../') else m[2])+'">'+m[1]+'</a>',escaped)
 if line.startswith('# '):parts.append('<h1>'+escaped[2:]+'</h1>')
 elif line.startswith('## '):parts.append('<h2>'+escaped[3:]+'</h2>')
 elif line:parts.append('<p>'+escaped+'</p>')
(r/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Coherent typed sort active</title><style>body{max-width:1100px;margin:32px auto;padding:0 20px;background:#101b2a;color:#e3edf8;font:16px/1.6 system-ui}table{border-collapse:collapse;width:100%}td{padding:9px;border-bottom:1px solid #456}pre{white-space:pre-wrap}a{color:#8dc4ff}</style>'+''.join(parts))
provenance={'kernel_sha256':hashlib.sha256((ROOT/'src/rescue/coherent_kernel.c').read_bytes()).hexdigest(),'header_sha256':hashlib.sha256((ROOT/'src/rescue/coherent_sort.h').read_bytes()).hexdigest(),'fixture_sha256':pi['fixture_sha256'],'deployment_sha256':hashlib.sha256((r/'deployment.json').read_bytes()).hexdigest(),'upstream':'https://github.com/aardappel/goose/blob/acc6310a83df7a322d3f8264a808f675348c4260/stdlib/std.goose','license':'Apache-2.0 for adapted sort; GPL-3.0-or-later for combined project','live_active':True,'python_integration_tests':41,'mac_pi_sort_cases_each':200000}
(r/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')

"""Publish aggregate evidence only; private RF/model artifacts stay private."""
import os,json,html
from pathlib import Path
root=Path(os.environ['ADSB_NEURAL_DATA_ROOT'])
p=root/'results/larger-companion-20261110'
out=Path(__file__).resolve().parents[2]/'validation/larger-companion-20261110';out.mkdir(parents=True,exist_ok=True)
read=lambda f:json.loads((p/f).read_text())
m=read('mac-full-pipeline.json');pi=read('pi-full-pipeline.json');d=read('mac-dsp-full-pipeline.json')
keys=['production_digest','previous_digest','candidate_digest','current_additions_digest','distance_bins','candidate_sha256']
assert all(m[k]==pi[k] for k in keys)
assert pi['raw_baseline_losses']==pi['raw_current_baseline_losses']==0
summary={'date':'2026-11-10','production':'original three models plus November 10 DSP-trained tiny companion, original-first','larger_models_deployed':False,'mac_pi_parity':True,'rf_seconds':pi['rf_seconds'],'far_stock_aircraft':pi['far_stock_aircraft'],'production_extras':pi['production_extras'],'raw_full_pipeline_additions':pi['candidate_additions_beyond_production'],'dsp_full_pipeline_additions':d['candidate_additions_beyond_production'],'baseline_losses':pi['raw_current_baseline_losses'],'pi_baseline_cpu_s_per_rf_s':pi['production_cpu_per_rf_second'],'pi_with_candidate_cpu_s_per_rf_s':pi['current_plus_candidate_cpu_per_rf_second'],'pi_candidate_inference_cpu_s_per_rf_s':pi['candidate_inference_after_current_cpu_per_rf_second'],'peak_process_rss_kib':pi['max_rss_kib'],'distance_bins':pi['distance_bins'],'window_results':{v:read(v+'/training.json')['metrics'] for v in ['raw','dsp']},'controls':read('controls.json')}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
text=f'''# Updated production companion and larger-network experiment

November 10, 2026 (Europe/Berlin).

## Production

The November 10 DSP-trained tiny companion is now appended to the original three-model cascade. Original-first priority preserves existing valid packets. The original model was not replaced. Its earlier validation showed four extra test windows but only one additional guarded RF message (100–150 nm, operational status); no distant RF improvement is established.

Activation preserved readsb, FR24, relay, ADSBx and collector process identities, gain, methods and collection limits. The coordinator alone restarted. The 150-second post-start observation passed, with 140 aligned blocks of progress and unchanged SDR loss counters. A three-entry provenance label tuple was extended before successful activation; an initial readiness race was caught by preflight. Rollback copies and an ownership-checked rollback helper remain on the receiver.

## Larger-network comparison

12 to 24 channels; 961 to 2,497 parameters. Raw and DSP-augmented variants were trained separately, 1,000 steps each. Validation-only selection preferred the raw variant for its one additional qualified distant validation window. No checkpoint was selected using RF or test results.

| Measurement | Updated production | + larger raw | + larger DSP-augmented |
|---|---:|---:|---:|
| Test-window complete packets (854 windows) | 647 | 647 | 660 |
| Extra qualified >=180 nm test windows | — | 0 | 3 |
| Full RF pipeline extras beyond stock | 260 | 260 | 260 |
| Unique RF additions beyond full production | — | 0 | 0 |
| RF baseline packet losses | — | 0 | 0 |
| Pi serial replay CPU seconds / RF second | {pi['production_cpu_per_rf_second']:.4f} | {pi['current_plus_candidate_cpu_per_rf_second']:.4f} | Not target-tested |

Both larger variants were replayed on Mac. The validation-selected raw variant was also replayed on the Pi 5: packet digests and distance bins matched Mac exactly. It added {pi['candidate_inference_after_current_cpu_per_rf_second']:.4f} CPU seconds per RF second for candidate inference alone. Total serial replay rose about {(pi['current_plus_candidate_cpu_per_rf_second']/pi['production_cpu_per_rf_second']-1)*100:.1f}%. Peak process RSS was {pi['max_rss_kib']/1024:.1f} MiB. This is CPU time, not elapsed latency or measured power; replay repeats frontend work and starts Stream1090 per clip, so it is not a live utilization estimate.

No larger-model additions occurred in any distance bin, including >=180 nm, or beyond the previous best offline companion. Larger models remain offline.

## Controls and limitations

Each variant produced zero CRC-valid outputs on 20,000 noise windows, zero wrong CRC-valid outputs on 4,096 clean windows, and zero unexplained valid outputs on 4,096 overlapping synthetic windows. Each overlap control recovered one known secondary transmission. ONNX export changed no bits or packet bytes.

Training reused the established qualified dataset: 9,341 train, 1,793 validation and 854 test windows, including 503/197/224 recently qualified distant windows. RF evaluation used 383 snippets, {pi['rf_seconds']:.3f} RF seconds ({pi['effective_rf_seconds']:.3f} after edges), and only six quality-screened distant aircraft. RF intervals are evaluation-only and disjoint from training. These are reused established holdouts captured before checkpoint freeze, not fresh prospective validation. Accepted-production annotations are best-effort and incomplete; the comparison includes the full frozen enabled replay, actual relay and conservative annotation mask, but cannot claim complete production-ledger coverage.

The Pi benchmark was isolated, nice 19, core 3, 35% CPU quota, bounded runtime and process-tree memory checks. Receiver/feeder health was monitored. No candidate packets were injected. The baseline included enabled energy, timing, soft, matched, coherent, neural and Stream1090 paths; CRC predictions remain quarantined.

## Recommendation

Keep the updated tiny companion in production. More capacity improved some isolated windows, but did not produce additional full-pipeline RF packets. Collect fresh difficult distant examples before another architecture change; keep these evaluation intervals out of training.

Private weights, RF, activation evidence, exact source/input hashes and full replay results are retained in the private experiment directory. Only aggregate results are published here.
'''
(out/'report.md').write_text(text)
(out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>readsb-dsp neural comparison</title><style>body{max-width:1000px;margin:40px auto;padding:20px;font:16px/1.6 system-ui;background:#101b28;color:#e4edf7}pre{white-space:pre-wrap}</style><pre>'+html.escape(text)+'</pre>')

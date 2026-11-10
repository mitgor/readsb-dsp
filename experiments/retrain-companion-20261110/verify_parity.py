from pathlib import Path
import json
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/retrain-20261110';P=R/'data/transfer/retrain-20261110/prepared';manifest={c['file']:c for c in json.loads((P/'cases.json').read_text())};m=json.loads((O/'mac-current.json').read_text());keys=['production_digest','previous_digest','candidate_digest','current_additions_digest','distance_bins','candidate_sha256'];out=[]
for i in range(1,4):
 d=json.loads((O/f'pi-{i}.json').read_text());assert all(m[k]==d[k] for k in keys);assert [(c['file'],round(c['rf_seconds']*2400000)) for c in m['cases']]==[(c['file'],round(c['rf_seconds']*2400000)) for c in d['cases']]
 total=0
 for c in d['cases']:
  n=manifest[c['file']]['sample_count'];assert round(c['rf_seconds']*2400000)==n;total+=n
 assert d['raw_baseline_losses']==d['raw_current_baseline_losses']==0
 out.append({'pass':i,'packet_and_timestamp_digests_exact':True,'distance_bins_exact':True,'canonical_rf_samples':total,'canonical_rf_seconds':total/2400000,'current_additions':d['candidate_additions_beyond_production'],'cpu_after_current_per_rf_second':d['candidate_inference_after_current_cpu_per_rf_second'],'max_rss_kib':d['max_rss_kib']})
(O/'pi-mac-parity.json').write_text(json.dumps(out,indent=2));(O/'parity-diagnostic-note.json').write_text(json.dumps({'initial_strict_duration_float_check_failed':True,'mac_summed_seconds':m['rf_seconds'],'pi_summed_seconds':json.loads((O/'pi-1.json').read_text())['rf_seconds'],'resolution':'All packet/payload/timestamp digests already matched exactly. Verify duration by integer original sample counts instead of exact float aggregation across Python/platform versions; no inference, model or packet tolerance change.'},indent=2));print(json.dumps(out,indent=2))

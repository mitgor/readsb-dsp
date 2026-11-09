"""Assert closed target parity against BOTH optimized C and actual C pipelines."""
from pathlib import Path
import subprocess,json,hashlib,statistics
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-sequence-20261109')
code=r'''
from pathlib import Path
import subprocess,json,hashlib,statistics
for u in ['adsb-rust-sequence-20261109','adsb-rust-sequence-opt-20261109']:assert subprocess.run(['systemctl','is-active','--quiet',u]).returncode!=0
D=Path('/dev/shm/adsb-rust-sequence-20261109');names=['benchmark.json','full-c.private.json','full-c-optimized.private.json','full-rust.private.json','protected.private.json','protected-optimized.private.json'];out={n:json.loads((D/n).read_text()) for n in names};out['library_sizes']={n:(D/'build'/(n+'.so')).stat().st_size for n in ['c','actual','rust']};print(json.dumps(out))
'''
x=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True));(D/'target-results.private.json').write_text(json.dumps(x)+'\n');b=x['benchmark.json'];assert b['all_arrays_bit_exact'] and b['windows']==3840 and b['controls']['noise']['valid']==0 and b['controls']['zero']['valid']==0
for n in ['protected.private.json','protected-optimized.private.json']:
 h=x[n];assert h['error'] is None and h['before']==h['after'];assert max(v['rss_kib'] for v in h['checks'])<1024*1024
runs={key:x[name] for key,name in [('actual_C','full-c.private.json'),('optimized_C','full-c-optimized.private.json'),('Rust','full-rust.private.json')]};assert all(len(z['cases'])==24 for z in runs.values())
for index,ref in enumerate(runs['actual_C']['cases']):
 for mode,data in runs.items():
  row=data['cases'][index];assert row['file']==ref['file']
  for field in ['candidates','accepted','audit','decisions']:assert row[field]==ref[field],(mode,ref['file'],field)
summary=dict(parity_passed=True,windows=b['windows'],exact_all_arrays=True,prepare_models=b['prepare_models'],controls=b['controls'],augmented_windows=b['augmented_windows'],kernel_median_cpu_s=b['median_cpu_s'],kernel_saving_vs_optimized_C_percent=b['median_saving_percent'],kernel_saving_vs_actual_C_percent=statistics.median(100*(1-r['cpu_s']['rust']/r['cpu_s']['actual']) for r in b['trials']),kernel_trials=b['trials'],full_RF_seconds=24,full_native_extras=sum(len(r['accepted']) for r in runs['actual_C']['cases']),full_raw_guarded_events_decisions_exact=True,full_native_worker_CPU_per_RF_second={mode:v['worker_cpu_s']/24 for mode,v in runs.items()},no_lost_or_added_packets=True,production_sequence_unchanged=True,library_sha256=b['libraries'],library_sizes=x['library_sizes'],max_recorded_RSS_MiB=max(v['rss_kib'] for name in ['protected.private.json','protected-optimized.private.json'] for v in x[name]['checks'])/1024,limits='Historical consumed regression RF; finite one-cycle whole-pipeline CPU per mode is descriptive, not repeated end-to-end timing or fresh range evidence. Stream child unchanged by sequence experiment and excluded from native-worker CPU.')
(D/'proof.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

"""Gate exact preserved releases against current kernels and persistent replay."""
from pathlib import Path
import json,subprocess,hashlib,collections
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/rust-revalidate-20261109'
code=r'''
from pathlib import Path
import subprocess,json,hashlib
D=Path('/dev/shm/adsb-rust-revalidate-20261109');assert subprocess.run(['systemctl','is-active','--quiet','adsb-rust-revalidate-20261109']).returncode!=0
names=['coherent.json','acquisition-controls.json','acquisition-packets.json','acquisition-cpu.json','full-c.private.json','full-rust.private.json','protected.private.json']
out={n:json.loads((D/n).read_text()) for n in names};out['current_reference_hashes']={n:hashlib.sha256((D/'reference/src/rescue'/n).read_bytes()).hexdigest() for n in ['_coherent.so','_coherent_pair.so','_pipeline_extended_neon.so','coherent_extended_opt.py']};out['candidate_hashes']={n:hashlib.sha256((D/'src/rescue'/n).read_bytes()).hexdigest() for n in ['_coherent.so','_coherent_pair.so','_acquisition_rust.so','coherent_extended_opt.py']};print(json.dumps(out))
'''
j=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True));(O/'isolated-results.private.json').write_text(json.dumps(j)+'\n');h=j['protected.private.json'];assert h['error'] is None and h['before']==h['after'];c=j['coherent.json'];assert c['windows']>=3000
for v in c['branches'].values():assert v['exact_all_arrays'] and v['parity']['packet_rows_flags_repairs_exact'] and v['cpu_saving_percent']>0
for v in c['controls'].values():assert v['augmented_windows']>=8192 and v['peak_selector_cases']>=500
assert j['acquisition-controls.json']['noise_crc_valid']==0 and j['acquisition-controls.json']['exact_scoring_and_candidate_cases']>=1201
assert all(v['exact_candidate_and_all_decoder_arrays'] for v in j['acquisition-packets.json']['budgets'].values())
assert all(v['exact_all_bytes'] for v in j['acquisition-cpu.json']['scenarios'].values());assert j['acquisition-cpu.json']['scenarios']['selector-16']['cpu_saving_percent']>0
base=j['full-c.private.json'];candidate=j['full-rust.private.json'];assert len(base['cases'])==24 and len(candidate['cases'])==24*6
reference={c['file']:c for c in base['cases']}
for row in candidate['cases']:
 old=reference[row['file']]
 for k in ['candidates','accepted','audit','decisions']:assert row[k]==old[k],(row['file'],k)
assert candidate['observed_wall_s']>=120
samples=[s['rss_kib'] for s in h['checks'] if s['phase']=='full-rust'];assert max(samples)<1024*1024
cpu_base=base['worker_cpu_s']/len(base['cases']);cpu_rust=candidate['worker_cpu_s']/len(candidate['cases']);proof=dict(parity_passed=True,stability_passed=True,coherent_windows=c['windows'],coherent_ordinary_saving_percent=c['branches']['base']['cpu_saving_percent'],coherent_pair_saving_percent=c['branches']['pair']['cpu_saving_percent'],acquisition_selector_saving_percent=j['acquisition-cpu.json']['scenarios']['selector-16']['cpu_saving_percent'],full_pipeline_RF_seconds_per_cycle=24,rust_RF_seconds=len(candidate['cases']),rust_soak_wall_s=candidate['observed_wall_s'],raw_and_guarded_events_exact_all_cycles=True,baseline_extras=sum(len(r['accepted']) for r in base['cases']),baseline_worker_cpu_per_RF_s=cpu_base,rust_worker_cpu_per_RF_s=cpu_rust,worker_CPU_change_percent=100*(cpu_rust/cpu_base-1),max_test_RSS_MiB=max(samples)/1024,current_reference_hashes=j['current_reference_hashes'],candidate_hashes=j['candidate_hashes'],production_unchanged=True,validation_snapshot=h['before'],scope='Kernel parity/controls and six-cycle full enabled pipeline replay. Finite stability evidence, not lifetime proof or fresh range improvement. Unmodified Stream1090/stock output stays original-first.')
(O/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))

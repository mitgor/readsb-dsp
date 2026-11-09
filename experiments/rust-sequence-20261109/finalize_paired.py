"""Freeze paired evidence, retaining the initial sequential timing comparison."""
from pathlib import Path
import subprocess,json,statistics,random,collections
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-sequence-20261109')
code=r'''
from pathlib import Path
import subprocess,json
assert subprocess.run(['systemctl','is-active','--quiet','adsb-rust-sequence-paired-v2-20261109']).returncode!=0
D=Path('/dev/shm/adsb-rust-sequence-20261109');p=json.loads((D/'paired.json').read_text());h=json.loads((D/'protected-paired-v2.private.json').read_text());assert h['error'] is None and h['before']==h['after'];assert p['all_raw_and_guarded_events_exact'] and len(p['pairs'])==48;print(json.dumps(dict(paired=p,health=h)))
'''
x=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True));(D/'paired-results.private.json').write_text(json.dumps(x)+'\n');proof=json.loads((D/'proof.json').read_text());(D/'proof-initial.json').write_text(json.dumps(proof,indent=2)+'\n');paired=x['paired'];groups=collections.defaultdict(lambda:[0.,0.])
for r in paired['pairs']:
 groups[r['file']][0]+=r['modes']['optimized_C']['cpu_s'];groups[r['file']][1]+=r['modes']['rust']['cpu_s']
values=list(groups.values());rng=random.Random(20261110);boot=[]
for _ in range(5000):
 sample=[rng.choice(values) for i in values];boot.append(100*(1-sum(v[1] for v in sample)/sum(v[0] for v in sample)))
boot.sort();ci=[boot[125],boot[4874]];proof['paired_full_pipeline']=dict(RF_seconds_per_mode=paired['paired_RF_seconds_per_mode'],warmup_RF_seconds=2,all_raw_and_guarded_events_exact=True,worker_CPU_per_RF_second=paired['worker_CPU_per_RF_second'],worker_CPU_reduction_percent=paired['worker_CPU_reduction_percent'],median_paired_reduction_percent=paired['median_paired_reduction_percent'],cluster_bootstrap_95_percent_interval=ci,interval_scope='24 RF-case clusters including both repeats; descriptive replay CPU interval, not prospective RF/energy or cross-device evidence.');proof['limits']+=' Initial sequential full-pipeline timings are retained but confounded by common-stage variation; use paired shared-worker timing for sequence-only worker-cost comparison.'
proof['max_recorded_RSS_MiB']=max(proof['max_recorded_RSS_MiB'],max(r['rss_kib'] for r in x['health']['checks'])/1024)
(D/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof['paired_full_pipeline'],indent=2))

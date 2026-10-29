"""Fresh-process six-way comparison on identical saved-window fixtures."""
import argparse,hashlib,json,platform,statistics,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'experiments/goose-coherent'))
from benchmark import compare
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=HERE/'.work');p.add_argument('--output',type=Path,required=True);p.add_argument('--trials',type=int,default=9);a=p.parse_args();w=a.work.resolve();n=struct.unpack('<Q',(w/'windows.bin').read_bytes()[:8])[0]
if a.output.exists():raise ValueError('Fresh output required')
variants=['c-old','c-current','goose','rust','rust-libc','rust-matched'];raw=[]
def run(name,loops):
 r=json.loads(subprocess.check_output([str(w/(name+'-bench')),str(w/'windows.bin'),str(loops),str(w/(name+'.out'))],text=True));r['variant']=name;r['cpu_us_per_window']=1e6*r['cpu_seconds']/(n*loops);return r
warm={name:run(name,1) for name in variants};parity={name:compare(w/'c-old.out',w/(name+'.out'),n) for name in variants}
loops=max(1,round(.35/warm['c-old']['cpu_seconds']))
for trial in range(a.trials):
 order=variants[trial%len(variants):]+variants[:trial%len(variants)]
 if trial%2:order=list(reversed(order))
 for name in order:
  r=run(name,loops);r['trial']=trial;raw.append(r);compare(w/'c-old.out',w/(name+'.out'),n)
 print('trial',trial+1,'of',a.trials,flush=True)
summary={}
for name in variants:
 rows=[s for s in raw if s['variant']==name];times=[s['cpu_us_per_window'] for s in rows]
 summary[name]={'median_cpu_us_per_window':statistics.median(times),'min_cpu_us_per_window':min(times),'max_cpu_us_per_window':max(times),'resident_bytes':1024*statistics.median(s['rss_after_work_kb'] for s in rows),'peak_rss_bytes':statistics.median(s['peak_rss_bytes'] for s in rows),'virtual_bytes':1024*statistics.median(s['vm_after_work_kb'] for s in rows),'binary_bytes':(w/(name+'-bench')).stat().st_size,'valid':rows[0]['valid'],'tracked':rows[0]['tracked']}
for v in summary.values():
 v['cpu_saving_vs_old_c_percent']=100*(1-v['median_cpu_us_per_window']/summary['c-old']['median_cpu_us_per_window']);v['cpu_saving_vs_current_c_percent']=100*(1-v['median_cpu_us_per_window']/summary['c-current']['median_cpu_us_per_window'])
out={'platform':platform.platform(),'windows':n,'fixture_sha256':hashlib.sha256((w/'windows.bin').read_bytes()).hexdigest(),'trials':a.trials,'loops':loops,'parity':parity,'summary':summary,'samples':raw,'toolchains':json.loads((w/'build.json').read_text()),'live_changed':False,'policy':'Same ordinary 41-bin coherent algorithm and ABI driver. Two process warmups; initialization and IO excluded. All ports use target libm. Safe Rust slice bounds checks remain. No fast math or target-native specialization. RSS includes whole standalone process; compiler/Python launch RSS excluded. Original C libc qsort; current C and Rust-matched port Goose typed sort; Rust default uses std sort_unstable_by; Rust-libc is sorting attribution control. No live input, deployment or extra-packet claim.'}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(summary,indent=2))

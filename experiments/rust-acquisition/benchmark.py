"""Same complete score arrays, candidate ordering, budgets and memory boundary."""
import argparse,hashlib,json,platform,struct,subprocess,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=HERE/'.work');p.add_argument('--output',type=Path,required=True);a=p.parse_args();w=a.work.resolve();assert not a.output.exists();flags=['-O3','-std=c11','-ffp-contract=off']+(['-D_DARWIN_C_SOURCE'] if platform.system()=='Darwin' else []);subprocess.run(['cc',*flags,str(HERE/'driver.c'),'-lm','-ldl','-o',str(w/'driver')],check=True)
result={'platform':platform.platform(),'fixture_sha256':hashlib.sha256((w/'blocks.bin').read_bytes()).hexdigest(),'trials':9,'scenarios':{},'build':json.loads((w/'build.json').read_text()),'live_changed':False}
for mode,budget in [(0,16),(1,16),(1,64),(1,256)]:
 name='scores' if not mode else 'selector-'+str(budget)
 def run(variant,loops):
  r=json.loads(subprocess.check_output([str(w/'driver'),str(w/(variant+'.so')),str(w/'blocks.bin'),str(loops),str(budget),str(mode),str(w/(variant+'.out'))],text=True));r['cpu_ns_per_power_sample']=r['cpu_s']*1e9/(r['samples']*loops);r['cpu_us_per_block']=r['cpu_s']*1e6/(r['blocks']*loops);return r
 warm=run('c',1);run('rust',1);assert (w/'c.out').read_bytes()==(w/'rust.out').read_bytes(),'output mismatch';loops=max(1,round(.25/warm['cpu_s']));samples={'c':[],'rust':[]}
 for trial in range(9):
  for variant in (['c','rust'] if trial%2==0 else ['rust','c']):samples[variant].append(run(variant,loops));assert (w/'c.out').read_bytes()==(w/'rust.out').read_bytes()
 summary={v:{'cpu_ns_per_power_sample':statistics.median(s['cpu_ns_per_power_sample'] for s in rows),'cpu_us_per_block':statistics.median(s['cpu_us_per_block'] for s in rows),'min_cpu_ns_per_sample':min(s['cpu_ns_per_power_sample'] for s in rows),'max_cpu_ns_per_sample':max(s['cpu_ns_per_power_sample'] for s in rows),'resident_bytes':statistics.median(s['resident_bytes'] for s in rows),'virtual_bytes':statistics.median(s['virtual_bytes'] for s in rows),'selected_per_fixture':rows[0]['selected'],'fallback_blocks':rows[0]['fallback_blocks']} for v,rows in samples.items()}
 result['scenarios'][name]={'summary':summary,'exact_all_bytes':True,'cpu_saving_percent':100*(1-summary['rust']['cpu_ns_per_power_sample']/summary['c']['cpu_ns_per_power_sample']),'loops':loops,'samples':samples};print(name,result['scenarios'][name]['cpu_saving_percent'],'percent saving',flush=True)
result['binary_bytes']={v:(w/(v+'.so')).stat().st_size for v in ['c','rust']};a.output.write_text(json.dumps(result,indent=2)+'\n')

"""Counterbalanced actual production ELF / rebuilt C++ / Rust CPU comparison."""
from pathlib import Path
import argparse,json,os,hashlib,time,statistics
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();D=a.root;B=D/'build-v3';previous=json.loads((D/'pi-final.json').read_text());data=json.loads((D/'input/dataset.private.json').read_text());rows=[];modes=['original','c','rust'];binary={m:(D/'stream-original' if m=='original' else B/('stream-'+m)) for m in modes}
for trial in range(7):
 totals={m:0. for m in modes}
 for i,c in enumerate(data['rows']):
  inp=D/'timing.iq';inp.write_bytes((D/'input/rf'/c['file']).read_bytes());order=modes[(trial+i)%3:]+modes[:(trial+i)%3]
  for m in order:
   output=D/'timing.out';error=D/'timing.err'
   with inp.open('rb') as fi,output.open('wb') as fo,error.open('wb') as fe:
    args=[str(binary[m]),'-s','2.4','-u','8'];pid=os.posix_spawn(str(binary[m]),args,os.environ,file_actions=[(os.POSIX_SPAWN_DUP2,fi.fileno(),0),(os.POSIX_SPAWN_DUP2,fo.fileno(),1),(os.POSIX_SPAWN_DUP2,fe.fileno(),2)]);_,status,r=os.wait4(pid,0)
   assert os.waitstatus_to_exitcode(status)==0;assert hashlib.sha256(output.read_bytes()).hexdigest()==previous['cases'][i]['modes'][m]['sha256'];totals[m]+=r.ru_utime+r.ru_stime
 rows.append(dict(trial=trial,cpu_s=totals,rust_saving_vs_production_percent=100*(1-totals['rust']/totals['original']),rust_saving_vs_control_percent=100*(1-totals['rust']/totals['c'])));print(rows[-1],flush=True)
x=dict(RF_seconds_per_trial=len(data['rows']),trials=rows,median_CPU_s={m:statistics.median(r['cpu_s'][m] for r in rows) for m in modes},median_rust_saving_vs_production_percent=statistics.median(r['rust_saving_vs_production_percent'] for r in rows),median_rust_saving_vs_control_percent=statistics.median(r['rust_saving_vs_control_percent'] for r in rows),binary_sha256={m:hashlib.sha256(binary[m].read_bytes()).hexdigest() for m in modes},all_raw_output_exact=True)
(D/'pi-production-timing.json').write_text(json.dumps(x,indent=2)+'\n')

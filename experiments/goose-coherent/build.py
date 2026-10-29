"""Emit portable Goose C and build isolated executables with identical C flags."""
import argparse,os,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
p=argparse.ArgumentParser();p.add_argument('--goose',type=Path);p.add_argument('--emit-only',action='store_true');p.add_argument('--work',type=Path,default=HERE/'.work');a=p.parse_args();a.work.mkdir(exist_ok=True,parents=True)
if a.goose:
 env={**os.environ,'GOOSE_HOME':str(a.work/'home')}
 cmd=[str(a.goose.resolve()),'-o',str(a.work/'coherent.c'),'--header',str(a.work/'coherent.h'),'--standalone','-O2',str(HERE/'coherent.goose')]
 with (a.work/'compile.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True)
if a.emit_only:raise SystemExit(0)
flags=['-O3','-std=c11','-ffp-contract=off','-DRESCUE_REFERENCE_SORT']+(['-D_DARWIN_C_SOURCE'] if sys.platform=='darwin' else [])
cc=os.environ.get('CC','cc')
for name,macros,sources in [('c-bench',[],[ROOT/'src/rescue/coherent_kernel.c']),('goose-bench',['-DGOOSE'],[a.work/'coherent.c']),('c-sort-bench',['-DSORT_CONTROL'],[HERE/'sort_control.c',a.work/'coherent.c'])]:
 subprocess.run([cc,*flags,*macros,'-I'+str(a.work),str(HERE/'driver.c'),*[str(p) for p in sources],'-lm','-lpthread','-o',str(a.work/name)],check=True)

"""Build all variants offline; never install or access the receiver/SDR."""
import argparse,json,os,platform,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=HERE/'.work');p.add_argument('--rustc',default=os.environ.get('RUSTC','rustc'));a=p.parse_args();w=a.work.resolve();w.mkdir(parents=True,exist_ok=True)
flags=['-O3','-std=c11','-ffp-contract=off']+(['-D_DARWIN_C_SOURCE'] if platform.system()=='Darwin' else [])
link=['-lm','-lpthread','-ldl']+(['-lgcc_s','-lutil','-lrt'] if platform.system()=='Linux' else [])
# No target-cpu=native or fast-math. Same ABI and C input/output driver for all.
rustflags=['--edition=2021','--crate-type','staticlib','-C','opt-level=3','-C','codegen-units=1','-C','panic=abort','-C','debuginfo=0','-C','strip=debuginfo']
commands=[]
def run(cmd):commands.append(cmd);subprocess.run(cmd,check=True)
for name,cfg in [('rust',[]),('rust-libc',['--cfg','sort_libc']),('rust-matched',['--cfg','sort_matched'])]:
 lib=w/('lib'+name+'.a');run([a.rustc,*rustflags,*cfg,str(HERE/'coherent.rs'),'-o',str(lib)])
 run(['cc',*flags,str(ROOT/'experiments/goose-coherent/driver.c'),str(lib),*link,'-o',str(w/(name+'-bench'))])
for name,extra in [('c-old',['-DRESCUE_REFERENCE_SORT']),('c-current',[])]:
 run(['cc',*flags,*extra,str(ROOT/'experiments/goose-coherent/driver.c'),str(ROOT/'src/rescue/coherent_kernel.c'),*link,'-o',str(w/(name+'-bench'))])
run(['cc',*flags,'-DGOOSE','-I'+str(w),str(ROOT/'experiments/goose-coherent/driver.c'),str(w/'coherent.c'),*link,'-o',str(w/'goose-bench')])
for name,cfg in [('rust',[]),('rust-matched',['--cfg','sort_matched'])]:
 run([a.rustc,'--edition=2021','--test','-C','opt-level=3',*cfg,str(HERE/'coherent.rs'),'-o',str(w/(name+'-tests'))]);run([str(w/(name+'-tests'))])
(w/'build.json').write_text(json.dumps({'rustc':subprocess.check_output([a.rustc,'--version','--verbose'],text=True),'cc':subprocess.check_output(['cc','--version'],text=True),'rustflags':rustflags,'cflags':flags,'link':link,'commands':commands},indent=2)+'\n')

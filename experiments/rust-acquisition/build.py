"""Build isolated scorer/selector shared libraries; no live installation."""
import argparse,json,platform,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=HERE/'.work');p.add_argument('--rustc',default='rustc');a=p.parse_args();w=a.work.resolve();w.mkdir(parents=True,exist_ok=True)
cflags=['-O3','-std=c11','-ffp-contract=off','-fPIC','-shared'];rflags=['--edition=2021','--crate-type','cdylib','-C','opt-level=3','-C','codegen-units=1','-C','panic=abort','-C','strip=debuginfo']
subprocess.run(['cc',*cflags,str(ROOT/'src/rescue/pipeline_extended_neon.c'),'-lm','-lpthread','-o',str(w/'c.so')],check=True)
subprocess.run([a.rustc,*rflags,str(HERE/'acquisition.rs'),'-o',str(w/'rust.so')],check=True)
subprocess.run([a.rustc,'--edition=2021','--test','-C','opt-level=3',str(HERE/'acquisition.rs'),'-o',str(w/'rust-tests')],check=True);subprocess.run([str(w/'rust-tests')],check=True)
(w/'build.json').write_text(json.dumps({'cc':subprocess.check_output(['cc','--version'],text=True),'rustc':subprocess.check_output([a.rustc,'--version','--verbose'],text=True),'cflags':cflags,'rustflags':rflags,'scope':'Same NEON on-sums lane order, rolling double arithmetic and selection policy; no fast math.'},indent=2)+'\n')

"""Offline C/Rust build: no production library writes or receiver input."""
import argparse,json,platform,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--rustc',default='rustc');p.add_argument('--work',type=Path,default=HERE/'.work');a=p.parse_args();w=a.work.resolve();w.mkdir(parents=True,exist_ok=True)
flags=['-O3','-std=c11','-ffp-contract=off']+(['-D_DARWIN_C_SOURCE'] if platform.system()=='Darwin' else []);rustflags=['--edition=2021','--crate-type','staticlib','-C','opt-level=3','-C','codegen-units=1','-C','panic=abort','-C','strip=debuginfo'];link=['-lm','-lpthread','-ldl']+(['-lgcc_s','-lutil','-lrt'] if platform.system()=='Linux' else [])
subprocess.run([a.rustc,*rustflags,str(HERE/'phase.rs'),'-o',str(w/'libphase.a')],check=True)
for name,sources in [('c',[ROOT/'src/rescue/research_science.c']),('rust',[w/'libphase.a'])]:subprocess.run(['cc',*flags,str(HERE/'driver.c'),*[str(p) for p in sources],*link,'-o',str(w/(name+'-bench'))],check=True)
(w/'build.json').write_text(json.dumps({'cc':subprocess.check_output(['cc','--version'],text=True),'rustc':subprocess.check_output([a.rustc,'--version','--verbose'],text=True),'cflags':flags,'rustflags':rustflags,'no_live_changes':True},indent=2)+'\n')

#!/usr/bin/env python3
"""Build ABI-compatible coherent Rust libraries into an explicit directory only."""
import argparse,json,os,platform,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--rustc',default=os.environ.get('RUSTC','rustc'));a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
version=subprocess.check_output([a.rustc,'--version','--verbose'],text=True)
if 'rustc 1.99.1' not in version:raise RuntimeError('Validated release uses Rust 1.99.1')
flags=['--edition=2021','--crate-type','staticlib','-C','opt-level=3','-C','codegen-units=1','-C','panic=abort','-C','debuginfo=0','-C','strip=debuginfo','-C','relocation-model=pic']
exports=['rescue_coherent','rescue_coherent_init','rescue_coherent_backend','rescue_coherent_peaks'];commands=[]
def run(cmd):commands.append(cmd);subprocess.run(cmd,check=True)
for mode,cfg in [('base',[]),('pair',['--cfg','coarse_pair'])]:
 archive=out/('libcoherent-'+mode+'.a');so=out/('_coherent'+('_pair' if mode=='pair' else '')+'.so')
 run([a.rustc,*flags,*cfg,str(ROOT/'src/rescue/coherent_rust.rs'),'-o',str(archive)])
 if platform.system()=='Darwin':
  link=['-Wl,-u,_rescue_coherent','-Wl,-u,_rescue_coherent_init','-Wl,-u,_rescue_coherent_backend',*[f'-Wl,-exported_symbol,_{s}' for s in exports],'-ldl']
 else:
  script=out/'exports.map';script.write_text('{global:'+''.join(s+';' for s in exports)+'local:*;};\n')
  link=['-Wl,-u,rescue_coherent','-Wl,-u,rescue_coherent_init','-Wl,-u,rescue_coherent_backend','-Wl,--gc-sections','-Wl,--version-script='+str(script),'-ldl','-lgcc_s','-lutil','-lrt']
 run(['cc','-O3','-std=c11','-ffp-contract=off','-fPIC','-shared',str(ROOT/'src/rescue/coherent_peaks.c'),str(archive),*link,'-lm','-lpthread','-o',str(so)])
 run(['strip','-S',str(so)])
(out/'build.json').write_text(json.dumps({'rustc':version,'flags':flags,'commands':commands,'policy':'No install or service access; output directory only; C peak helper retained unchanged.'},indent=2)+'\n')

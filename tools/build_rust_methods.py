#!/usr/bin/env python3
"""Build default Rust acquisition/EM and unchanged C compatibility libraries."""
import argparse,json,os,platform,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--rustc',default=os.environ.get('RUSTC','rustc'));a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
version=subprocess.check_output([a.rustc,'--version','--verbose'],text=True)
if 'rustc 1.99.1' not in version:raise RuntimeError('Validated Rust method release requires Rust 1.99.1')
flags=['--edition=2021','--crate-type','cdylib','-C','opt-level=3','-C','codegen-units=1','-C','panic=abort','-C','strip=debuginfo'];commands=[]
def run(cmd):commands.append(cmd);subprocess.run(cmd,check=True)
for output,source in [('_acquisition_rust.so','acquisition_rust.rs'),('_science_em_rust.so','science_em_rust.rs')]:run([a.rustc,*flags,str(ROOT/'src/rescue'/source),'-o',str(out/output)])
for output,source in [('_science.so','research_science.c'),('_pipeline_extended_neon.so','pipeline_extended_neon.c')]:run(['cc','-O3','-std=c11','-ffp-contract=off','-fPIC','-shared',str(ROOT/'src/rescue'/source),'-lm','-lpthread','-o',str(out/output)])
(out/'build.json').write_text(json.dumps({'rustc':version,'flags':flags,'commands':commands,'policy':'Output only; caller chooses install. C compatibility APIs remain unchanged.'},indent=2)+'\n')

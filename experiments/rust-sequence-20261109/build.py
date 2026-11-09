"""Isolated Rust sequence build plus optimized v3 C control; no install."""
import argparse,json,subprocess,hashlib,platform
from pathlib import Path
H=Path(__file__).resolve().parent;C=H.parents[1]
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--rustc',default='rustc');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);commands=[]
def run(cmd):commands.append(list(map(str,cmd)));subprocess.run(cmd,check=True)
rf=['--edition=2021','--crate-type=cdylib','-C','opt-level=3','-C','panic=abort','-C','codegen-units=1'];cf=['-O3','-std=c11','-ffp-contract=off','-fPIC','-shared']
run([a.rustc,*rf,H/'sequence.rs','-o',a.out/'rust.so']);run(['cc',*cf,C/'src/rescue/pipeline_v3.c','-lm','-o',a.out/'c.so'])
(a.out/'build.json').write_text(json.dumps(dict(commands=commands,rustc=subprocess.check_output([a.rustc,'--version','--verbose'],text=True),cc=subprocess.check_output(['cc','--version'],text=True),flags=dict(c=cf,rust=rf),source_hashes={str(f.relative_to(C)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [H/'sequence.rs',C/'src/rescue/coherent_rust.rs',C/'src/rescue/science_em_rust.rs',C/'src/rescue/pipeline_v3.c']}),indent=2)+'\n')

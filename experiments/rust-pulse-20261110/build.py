"""Isolated exact-arithmetic C/Rust pulse builds; never install here."""
from pathlib import Path
import argparse,subprocess,json,hashlib
H=Path(__file__).resolve().parent;C=H.parents[1];p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--rustc',default='rustc');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);commands=[]
def run(c):commands.append(list(map(str,c)));subprocess.run(c,check=True)
run([a.rustc,'--edition=2021','--crate-type=cdylib','-C','opt-level=3','-C','codegen-units=1','-C','panic=abort','-C','strip=debuginfo',H/'pulse.rs','-o',a.out/'rust.so']);run(['cc','-O3','-std=c11','-ffp-contract=off','-shared','-fPIC',C/'src/rescue/pulse_discriminant.c','-lm','-o',a.out/'c.so'])
(a.out/'build.json').write_text(json.dumps(dict(commands=commands,rustc=subprocess.check_output([a.rustc,'--version','--verbose'],text=True),cc=subprocess.check_output(['cc','--version'],text=True),sources={str(p.relative_to(C)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [H/'pulse.rs',C/'src/rescue/pulse_discriminant.c']}),indent=2)+'\n')

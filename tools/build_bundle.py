#!/usr/bin/env python3
"""Build this source tree only. Never install, open SDR or touch services."""
import argparse,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
KERNELS={'_frontend':'frontend','_research_interp':'research_interp','_coherent':'coherent_kernel',
 '_pipeline_native':'pipeline_native','_pipeline_v3':'pipeline_v3','_sequence':'research_sequence',
 '_acquisition_native':'acquisition_native','_fir_cached':'fir_cached',
 '_pipeline_extended_neon':'pipeline_extended_neon','_pulse_discriminant':'pulse_discriminant',
 '_candidate_context':'candidate_context','_pipeline_buffers':'pipeline_buffers'}
def build(native_only=False,rtlsdr=False,jobs=2,coherent_backend="c",methods_backend="c"):
 if methods_backend not in ('c','rust'):raise ValueError('methods_backend must be c or rust')
 if coherent_backend not in ('c','rust'):raise ValueError('coherent_backend must be c or rust')
 if type(jobs) is not int or not 1<=jobs<=16:raise ValueError('jobs must be 1..16')
 src=ROOT/'src/rescue'
 with tempfile.TemporaryDirectory(dir=src) as tmp:
  for name,source in {**KERNELS,'_coherent_pair':'coherent_kernel'}.items():
   if coherent_backend=='rust' and name in ('_coherent','_coherent_pair'):continue
   flags=['-DRESCUE_COARSE_PAIR'] if name=='_coherent_pair' else []
   out=Path(tmp)/(name+'.so')
   subprocess.run([os.environ.get('CC','cc'),'-O3','-std=c11','-ffp-contract=off','-fPIC','-shared',*flags,str(src/(source+'.c')),'-lm','-o',str(out)],check=True)
   os.replace(out,src/out.name)
  if coherent_backend=='rust':
   subprocess.run([sys.executable,str(ROOT/'tools/build_coherent_rust.py'),'--output',tmp],check=True)
   for name in ('_coherent.so','_coherent_pair.so'):os.replace(Path(tmp)/name,src/name)
  if methods_backend=='rust':
   subprocess.run([sys.executable,str(ROOT/'tools/build_rust_methods.py'),'--output',tmp],check=True)
   for name in ('_acquisition_rust.so','_science_em_rust.so','_science.so'):os.replace(Path(tmp)/name,src/name)
  else:
   # C rebuild explicitly resets optional defaults from an earlier Rust build.
   for name in ('_acquisition_rust.so','_science_em_rust.so'):(src/name).unlink(missing_ok=True)
 if not native_only:
  subprocess.run(['make','-C',str(ROOT/'readsb'),'clean'],check=True)
  subprocess.run(['make','-C',str(ROOT/'readsb'),f'-j{jobs}','RTLSDR='+('yes' if rtlsdr else 'no')],check=True)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native-only',action='store_true');p.add_argument('--rtlsdr',action='store_true');p.add_argument('--jobs',type=int,default=2);p.add_argument('--coherent-backend',choices=('c','rust'),default='c');p.add_argument('--methods-backend',choices=('c','rust'),default='c');a=p.parse_args();build(a.native_only,a.rtlsdr,a.jobs,a.coherent_backend,a.methods_backend)

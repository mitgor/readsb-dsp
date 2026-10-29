#!/usr/bin/env python3
"""Build this source tree only. Never install, open SDR or touch services."""
import argparse,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
KERNELS={'_frontend':'frontend','_research_interp':'research_interp','_coherent':'coherent_kernel',
 '_pipeline_native':'pipeline_native','_pipeline_v3':'pipeline_v3','_sequence':'research_sequence',
 '_acquisition_native':'acquisition_native','_fir_cached':'fir_cached',
 '_pipeline_extended_neon':'pipeline_extended_neon','_pulse_discriminant':'pulse_discriminant',
 '_candidate_context':'candidate_context','_pipeline_buffers':'pipeline_buffers'}
def build(native_only=False,rtlsdr=False,jobs=2):
 if type(jobs) is not int or not 1<=jobs<=16:raise ValueError('jobs must be 1..16')
 src=ROOT/'src/rescue'
 with tempfile.TemporaryDirectory(dir=src) as tmp:
  for name,source in {**KERNELS,'_coherent_pair':'coherent_kernel'}.items():
   flags=['-DRESCUE_COARSE_PAIR'] if name=='_coherent_pair' else []
   out=Path(tmp)/(name+'.so')
   subprocess.run([os.environ.get('CC','cc'),'-O3','-std=c11','-ffp-contract=off','-fPIC','-shared',*flags,str(src/(source+'.c')),'-lm','-o',str(out)],check=True)
   os.replace(out,src/out.name)
 if not native_only:
  subprocess.run(['make','-C',str(ROOT/'readsb'),'clean'],check=True)
  subprocess.run(['make','-C',str(ROOT/'readsb'),f'-j{jobs}','RTLSDR='+('yes' if rtlsdr else 'no')],check=True)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native-only',action='store_true');p.add_argument('--rtlsdr',action='store_true');p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.native_only,a.rtlsdr,a.jobs)

"""Common entrypoint; builds and replays do not install or activate services."""
import argparse,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser(prog='deadsb',description='deadsb dsp / readsb-dsp')
 p.add_argument('--version',action='version',version='deadsb dsp 0.2.0')
 sub=p.add_subparsers(dest='command',required=True)
 b=sub.add_parser('build');b.add_argument('--native-only',action='store_true');b.add_argument('--rtlsdr',action='store_true');b.add_argument('--jobs',type=int,default=2)
 d=sub.add_parser('dashboard');d.add_argument('--port',type=int,default=8912);d.add_argument('--runtime',type=Path,default=Path('/run/deadsb'));d.add_argument('--budget-config',type=Path,default=ROOT/'config/cpu-budget.json')
 r=sub.add_parser('benchmark');r.add_argument('--iq',type=Path,required=True);r.add_argument('--output',type=Path,required=True);r.add_argument('--profile',type=int,choices=range(5),default=0)
 sub.add_parser('shadow',help='Pass arguments to the stock-first rescue coordinator')
 a,extra=p.parse_known_args()
 if not (ROOT/'readsb/Makefile').exists() or not (ROOT/'models').is_dir():
  p.error('Use a source checkout with pip install -e .; standalone wheels do not contain the full readsb/model tree')
 if a.command=='shadow':return subprocess.call([sys.executable,'-m','rescue.shadow',*extra])
 if extra:p.error('Unrecognized arguments: '+' '.join(extra))
 if a.command=='build':
  return subprocess.call([sys.executable,str(ROOT/'tools/build_bundle.py'),*(['--native-only'] if a.native_only else []),*(['--rtlsdr'] if a.rtlsdr else []),'--jobs',str(a.jobs)])
 if a.command=='dashboard':
  from .dashboard import serve
  serve(a.runtime,a.budget_config,a.port)
 elif a.command=='benchmark':
  from .benchmark import benchmark
  benchmark(ROOT,a.iq,a.output,a.profile)
 return 0
if __name__=='__main__':raise SystemExit(main())

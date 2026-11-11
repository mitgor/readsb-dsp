"""Bounded isolated Pi parity/preemption test, protected services read-only."""
import pathlib,subprocess,runpy,json,time,os,threading,hashlib
R=pathlib.Path('/dev/shm/adsb-guard-timeout-20261111');S=R/'stage';O=R/'results';O.mkdir(exist_ok=True);G=runpy.run_path('/usr/local/sbin/adsb-stream1090-lowlatency-mode');before=G['snapshot']();G['healthy'](before,before);G['capture']();stop=threading.Event();errors=[];health=[]
def monitor():
 while not stop.wait(5):
  try:s=G['snapshot']();G['healthy'](before,s);G['capture']();health.append(s)
  except BaseException as exc:errors.append(repr(exc));return
def run(args,name,env=None):
 with (O/name).open('w') as f:
  p=subprocess.Popen([str(x) for x in args],stdout=f,stderr=subprocess.STDOUT,env=env)
  end=time.monotonic()+180
  while p.poll() is None:
   if errors or time.monotonic()>end:p.terminate();raise RuntimeError(errors or 'owned command deadline')
   time.sleep(.2)
  assert p.returncode==0,(name,p.returncode)
threading.Thread(target=monitor,daemon=True).start()
try:
 flags=['c++','-O3','-std=c++20','-ffast-math','-mcpu=cortex-a76','-DSTATS_ENABLED=0','-DSTREAM1090_MIN_SNR=2.5','-DSTREAM1090_PREAMBLE_GATE=1','-DSTREAM1090_PREAMBLE_THRESHOLD=1.2','-fPIC','-I'+str(R/'readsb/contrib/stream1090-native')]
 run(flags+['-shared',R/'readsb/contrib/stream1090-native/incremental.cpp','-o',S/'bin/incremental.so'],'build.log')
 run(['python3',R/'experiments/guard-timeout-20261111/controls.py'],'controls.log')
 run(['c++','-std=c++20','-rdynamic','-I'+str(R/'readsb/contrib/stream1090-native'),R/'experiments/guard-timeout-20261111/preempt.cpp','-ldl','-o',R/'preempt'],'preempt-build.log')
 d=json.loads((S/'capture/capture.private.json').read_text());raw=S/'capture'/d['cases'][0]['file'];pre=[]
 for label,lib,expected in [('old',R/'old-incremental.so',-4),('new',S/'bin/incremental.so',0)]:
  p=subprocess.Popen([str(R/'preempt'),str(lib),str(raw)],stdout=subprocess.PIPE,text=True);_,status=os.waitpid(p.pid,os.WUNTRACED);assert os.WIFSTOPPED(status);time.sleep(.25);os.kill(p.pid,18);out=p.communicate(timeout=10)[0];row=json.loads(out);assert row['rc']==expected,row;pre.append(dict(version=label,**row,forced_deschedule_s=.25))
 env=dict(os.environ,PYTHONPATH=str(S/'runtime'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',TMPDIR=str(S/'tmp'));env['PATH']=os.environ['PATH']
 run(['/home/pi/adsb-neural-rescue/.venv/bin/python',S/'replay-half.py','--capture',S/'capture','--libraries',S/'bin','--legacy',S/'legacy','--output',O/'integration.json'],'replay.log',env)
 result=dict(passed=True,preemption=pre,integration=json.loads((O/'integration.json').read_text()),before=before,after=G['snapshot'](),health=health,errors=errors,production_actions=[])
 G['healthy'](before,result['after']);G['capture']();(O/'pi.json').write_text(json.dumps(result,indent=2));print(json.dumps(dict(passed=True,preemption=pre,retained=result['integration']['retained'],union=result['integration']['recorded_union'])))
finally:
 stop.set();(O/'health.private.json').write_text(json.dumps(dict(samples=health,errors=errors),indent=2))

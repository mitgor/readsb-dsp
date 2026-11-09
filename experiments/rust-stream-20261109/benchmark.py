"""Exact full stdout parity and counterbalanced child CPU/RSS, isolated RF files."""
from pathlib import Path
import argparse,json,os,hashlib,statistics,time,platform,subprocess
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--trials',type=int,default=5);p.add_argument('--mac',action='store_true');p.add_argument('--build',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();D=a.root;B=a.build or D/('mac-build' if a.mac else 'build');data=json.loads((D/'input/dataset.private.json').read_text());modes=['c','rust'] if a.mac else ['original','c','rust'];samples=[];cases=[]
def run(binary,raw,name,args=['-s','2.4','-u','8']):
 inp=D/'scratch.iq';out=D/'scratch.out';err=D/'scratch.err';inp.write_bytes(raw)
 with inp.open('rb') as fi,out.open('wb') as fo,err.open('wb') as fe:
  start=time.monotonic();pid=os.posix_spawn(str(binary),[str(binary),*args],os.environ,file_actions=[(os.POSIX_SPAWN_DUP2,fi.fileno(),0),(os.POSIX_SPAWN_DUP2,fo.fileno(),1),(os.POSIX_SPAWN_DUP2,fe.fileno(),2)]);_,status,usage=os.wait4(pid,0);wall=time.monotonic()-start
 assert os.waitstatus_to_exitcode(status)==0,(name,err.read_text()[-1000:]);return out.read_bytes(),dict(cpu_s=usage.ru_utime+usage.ru_stime,rss_kib=usage.ru_maxrss/(1024 if a.mac else 1),wall_s=wall)
def binary(mode):return D/'stream-original' if mode=='original' else B/('stream-'+mode)
control=subprocess.check_output([str(B/'state-test')]);state=json.loads(control)
# Reference C++, Rust, then actual running binary must emit identical bytes.
for i,c in enumerate(data['rows']):
 raw=(D/'input/rf'/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256'];reference=None;rr={}
 for mode in modes:
  out,metrics=run(binary(mode),raw,mode);rr[mode]=dict(sha256=hashlib.sha256(out).hexdigest(),bytes=len(out),**metrics)
  if reference is None:reference=out
  else:assert out==reference,('full-output parity',c['file'],mode)
  dest=D/'outputs'/mode;dest.mkdir(parents=True,exist_ok=True);(dest/(c['file']+'.avr')).write_bytes(out)
 cases.append(dict(file=c['file'],modes=rr));print('parity',i+1,len(data['rows']),flush=True)
# Deterministic flat, impulse/clipping and RF noise controls; all output must match.
import random
rng=random.Random(261109);controls={'dc':bytes([127])*4802400,'clipping':bytes([0,255])*2401200,'noise':rng.randbytes(4802400)};control_results={}
for name,raw in controls.items():
 outputs={mode:run(binary(mode),raw,name)[0] for mode in modes};assert len(set(outputs.values()))==1,(name,'control parity');control_results[name]=dict(bytes=len(next(iter(outputs.values()))),sha256=hashlib.sha256(next(iter(outputs.values()))).hexdigest())
for trial in range(a.trials):
 totals={mode:dict(cpu_s=0.,max_rss_kib=0.,wall_s=0.) for mode in ['c','rust']}
 for i,c in enumerate(data['rows']):
  raw=(D/'input/rf'/c['file']).read_bytes();order=['c','rust'] if (trial+i)%2==0 else ['rust','c']
  for mode in order:
   out,m=run(binary(mode),raw,mode);assert hashlib.sha256(out).hexdigest()==cases[i]['modes'][mode]['sha256'];t=totals[mode];t['cpu_s']+=m['cpu_s'];t['wall_s']+=m['wall_s'];t['max_rss_kib']=max(t['max_rss_kib'],m['rss_kib'])
 samples.append(dict(trial=trial,modes=totals,saving_percent=100*(1-totals['rust']['cpu_s']/totals['c']['cpu_s'])));print('trial',trial,samples[-1],flush=True)
kernel=[]
for i in range(7):
 row={}
 for mode in (['c','rust'] if i%2==0 else ['rust','c']):
  out,m=run(B/'state-test',b'',mode,[mode]);row[mode]=dict(**m,digest=out.decode().strip())
 assert row['c']['digest']==row['rust']['digest'];kernel.append(row)
# A noinline/-pg attribution build only: not used for speed comparison.
profile=None
if not a.mac and (B/'stream-profile').exists():
 gmons=[]
 for i,c in enumerate(data['rows']):
  os.environ['GMON_OUT_PREFIX']=str(D/f'gmon-{i}');raw=(D/'input/rf'/c['file']).read_bytes();out,_=run(B/'stream-profile',raw,'profile');assert hashlib.sha256(out).hexdigest()==cases[i]['modes']['c']['sha256']
 del os.environ['GMON_OUT_PREFIX'];gmons=list(D.glob('gmon-*.*'));profile=subprocess.check_output(['gprof','-b',str(B/'stream-profile'),*[str(x) for x in gmons]],text=True);(D/'gprof.txt').write_text(profile)
# Linux wait4 launch high-water can include the Python spawn image. Measure decoder
# RSS separately through a small exec/fork launcher; keep this out of CPU trials.
(D/'pre-memory.private.json').write_text(json.dumps(dict(cases=cases,trials=samples,kernel_trials=kernel,controls=control_results,state=state))+'\n')
resident={}
if not a.mac:
 for mode in modes:
  values=[]
  for c in data['rows'][:3]:
   mem=D/'memory.txt'
   z=subprocess.run([str(D/'memory-launcher'),str(mem),str(binary(mode)),'-s','2.4','-u','8'],input=(D/'input/rf'/c['file']).read_bytes(),capture_output=True,check=True)
   assert hashlib.sha256(z.stdout).hexdigest()==next(r for r in cases if r['file']==c['file'])['modes'][mode]['sha256']
   values.append(int(mem.read_text().strip()))
  resident[mode]=dict(samples_kib=values,max_kib=max(values))
summary=dict(platform=platform.platform(),state_parity=state,RF_seconds=len(cases),exact_full_output=True,controls=control_results,cases=cases,trials=samples,kernel_trials=kernel,median_cpu_saving_percent=statistics.median(x['saving_percent'] for x in samples),median_kernel_cpu_saving_percent=100*(1-statistics.median(x['rust']['cpu_s'] for x in kernel)/statistics.median(x['c']['cpu_s'] for x in kernel)),max_rss_kib={k:max(s['modes'][k]['max_rss_kib'] for s in samples) for k in ['c','rust']},binary_hashes={mode:hashlib.sha256(binary(mode).read_bytes()).hexdigest() for mode in modes},production_changed=False,isolated_decoder_rss=resident,raw_wait4_rss_may_include_spawn_context=True)
(a.output or D/('mac.json' if a.mac else 'pi.json')).write_text(json.dumps(summary,indent=2)+'\n')
print('SUMMARY',summary['median_cpu_saving_percent'],summary['median_kernel_cpu_saving_percent'],summary['max_rss_kib'],flush=True)

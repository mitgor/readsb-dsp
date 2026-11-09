"""Unmodified Stream1090 binary, shortened RF inputs; no production endpoints."""
import argparse,bisect,collections,hashlib,json,os,resource,statistics,subprocess,time,platform
from pathlib import Path
from rescue.stream1090_shadow import parse_avr,compare
RATE=2400000;HALO=600

def offsets(candidates,stock,identified=False):
 by=collections.defaultdict(list)
 for r in stock:by[r['message_hex']].append(r['ticks'])
 for v in by.values():v.sort()
 out=[]
 for tick,p in candidates:
  a=by[p];i=bisect.bisect_left(a,tick);near=a[max(0,i-1):i+1]
  if near:
   d=min(near,key=lambda t:abs(t-tick))-tick
   if abs(d)<=60000:out.append((tick+d,p,d) if identified else d)
 return out

def unique_offsets(history):
 by=collections.defaultdict(list)
 for _,rows in history:
  for tick,payload,delta in rows:by[(tick,payload)].append(delta)
 return [statistics.median(v) for v in by.values()]

def clock(values):
 if len(values)<10:return None
 offset=int(statistics.median(values));mad=statistics.median(abs(d-offset) for d in values)
 return offset if mad<=360 else None

def quantile(values):
 v=sorted(values)
 return dict(n=len(v),median_s=statistics.median(v),p95_s=v[min(len(v)-1,int(.95*len(v)))],max_s=max(v)) if v else dict(n=0)

def execute(c,raw,ms,binary,pace):
 samples=ms*2400;cores=2400000//samples;history=[];pending=[];strict=[];rolling=[];cpu=0.;parent=0.;walls=[];fail=collections.Counter();virtual=0.;origin=time.monotonic()
 for i in range(cores):
  start=i*samples;first=c['first']+start;blob=raw[start*2:(start+samples+1200)*2];assert len(blob)==(samples+1200)*2
  ready=(start+samples+1200)/RATE
  if pace:
   left=origin+ready-time.monotonic()
   if left>0:time.sleep(left)
  before=resource.getrusage(resource.RUSAGE_CHILDREN);mark=time.monotonic();run=subprocess.run([str(binary),'-s','2.4','-u','8'],input=blob,capture_output=True,timeout=5,check=True);after=resource.getrusage(resource.RUSAGE_CHILDREN);cp=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime;cpu+=cp;wall=time.monotonic()-mark;walls.append(wall);virtual=max(ready,virtual)+cp;finished=time.monotonic()-origin if pace else virtual
  mark=time.process_time();candidates=list(parse_avr(run.stdout,first));lo=(first+600)*5;hi=lo+samples*5;stock=[r for r in c['stock'] if lo-60000<=r['ticks']<hi+60000];audit,rr=compare(candidates,[(r['ticks'],r['message_hex']) for r in stock])
  if audit['aligned']:
   strict.extend(dict(source='stream1090',ticks=t,message_hex=p,ready_s=finished) for t,p in rr if lo<=t<hi)
  else:fail['strict_unaligned_clips']+=1
  matched=offsets(candidates,stock,identified=True);ds=[r[2] for r in matched];history.append((hi,matched));history=[h for h in history if h[0]>=hi-12000000];pending.append((lo,hi,candidates,ds));d=clock(unique_offsets(history))
  if d is not None:
   remaining=[]
   for a,b,rows,observed in pending:
    # Same minimum and MAD as current calibration; reject a disagreeing clip.
    if observed and statistics.median(abs(v-d) for v in observed)>360:fail['rolling_disagreeing_clip']+=1;continue
    if hi-b>12000000:fail['rolling_expired_clip']+=1;continue
    rolling.extend(dict(source='stream1090',ticks=t+d,message_hex=p,ready_s=finished) for t,p in rows if a<=t+d<b)
   pending=remaining
  parent+=time.process_time()-mark
 fail['rolling_unaligned_clips']=len(pending)
 def clean(rows):
  # Exclude stock and duplicate seam decodes after calibration, same tolerance.
  stockidx=collections.defaultdict(list);seen=collections.defaultdict(list);out=[]
  for r in c['stock']:stockidx[r['message_hex']].append(r['ticks'])
  for v in stockidx.values():v.sort()
  for r in sorted(rows,key=lambda r:(r['ready_s'],r['ticks'])):
   p=r['message_hex'];t=r['ticks'];v=stockidx[p];i=bisect.bisect_left(v,t-1440)
   if i<len(v) and v[i]<=t+1440:continue
   if any(abs(t-v)<=1440 for v in seen[p]):continue
   seen[p].append(t);r['ready_age_s']=r['ready_s']-(t-c['first']*5)/12000000;out.append(r)
  return out
 return dict(core_ms=ms,child_cpu_s=cpu,coordinator_cpu_s=parent,process_wall_s=walls,strict=clean(strict),rolling=clean(rolling),failure_counts=dict(fail),invocations=cores)

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--pace',action='store_true');p.add_argument('--cores',type=int,nargs='+',default=[1000,500,250,100]);a=p.parse_args();assert not a.output.exists();data=json.loads((a.input/'dataset.private.json').read_text());results=[]
 for i,c in enumerate(data['rows']):
  raw=(a.input/'rf'/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256'];modes=a.cores;modes=modes[i%len(modes):]+modes[:i%len(modes)];rr=[]
  for ms in modes:
   j=execute(c,raw,ms,a.binary,a.pace);rr.append(j)
   print(json.dumps(dict(case=i,ms=ms,cpu_s=j['child_cpu_s'],strict=len(j['strict']),rolling=len(j['rolling']))),flush=True)
  results.append(dict(file=c['file'],variants=rr));a.output.with_suffix('.progress.json').write_text(json.dumps(dict(completed_cases=len(results),total=len(data['rows']))))
 result=dict(hardware=platform.platform(),binary_sha256=hashlib.sha256(a.binary.read_bytes()).hexdigest(),native_RF_clock=a.pace,latency_scope='Stream candidate-ready RF age, not final admission/relay/cloud; actual replay wall under target cgroup when paced; CPU-based FIFO estimate on Mac. Historical stock arrival times unavailable; stock clock assumed available at window close.',dataset_sha256=hashlib.sha256((a.input/'dataset.private.json').read_bytes()).hexdigest(),results=results)
 a.output.write_text(json.dumps(result)+'\n')
if __name__=='__main__':main()

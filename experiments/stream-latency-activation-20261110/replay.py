"""Saved-RF integration gate. Real production hooks with a private temp outbox."""
import argparse,concurrent.futures,hashlib,json,sys,tempfile,time,threading
from pathlib import Path
from types import SimpleNamespace
from collections import defaultdict
from rescue.lowlatency_stream import LowLatency,CompletionTap
from rescue.streaming import TOTAL,CORE
from rescue.shadow import evaluate
from rescue.stock_history import StockHistory

def main():
 p=argparse.ArgumentParser();p.add_argument('--capture',type=Path,required=True);p.add_argument('--libraries',type=Path,required=True);p.add_argument('--legacy',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 sys.path.append(str(a.legacy));from benchmark import Energy
 d=json.loads((a.capture/'capture.private.json').read_text());assert not d['errors'];cc=d['cases'];epoch=cc[0]['epoch'];first=cc[0]['first'];start=cc[0]['wall'];raws=[]
 for c in cc:
  raw=(a.capture/c['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256'];raws.append(raw)
 # Feed the actual non-overlapping copied tap stream, including the final halo.
 iq=b''.join(r[:CORE*2] for r in raws)+raws[-1][CORE*2:];jobs=[]
 for i,c in enumerate(cc):
  for j,at in enumerate(range(0,TOTAL,120000)):
   due=c['wall']-start+min(TOTAL,at+120600)/2400000;jobs.append((due,i,j))
 stock=sorted(d['stock'],key=lambda r:r['arrival']);known=StockHistory();s=0;k=0;n=0;emitted=[];cfg={'enabled':True}
 for name in ['batch','incremental','admission','dedup']:
  f=a.libraries/(name+'.so');cfg[name]=dict(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest())
 with tempfile.TemporaryDirectory(prefix='stream-live-integration-') as root:
  root=Path(root);config=root/'config.json';config.write_text(json.dumps(cfg));live=SimpleNamespace(lock=threading.RLock(),health={});low=LowLatency(live,cfg,root,config);energy=Energy();energy_rows=defaultdict(list);closed={};startmono=time.monotonic()
  try:
   while True:
    live.health['aircraft_unix']=time.time();elapsed=time.monotonic()-startmono;assert not low.failed,low.error
    if elapsed>=35:raise RuntimeError(dict(replay='deadline',stock=s,iq=k,energy=n,status=low.report(),windows={str(j):{k:w[k] for k in ('native_done','energy_done','finalized','native_watermark','energy_watermark')} for j,w in low.bridge.windows.items()}))
    while s<len(stock) and stock[s]['arrival']<=start+elapsed:
     row=stock[s];known.append(row);low.offer_stock(row);s+=1
    while k<len(iq)//2 and (min(k+15000,len(iq)//2)/2400000)<=elapsed:
     j=min(k+15000,len(iq)//2);low.offer_iq(epoch,first+k,iq[2*k:2*j]);k=j
    low.tick()
    while n<len(jobs) and jobs[n][0]<=elapsed:
     _,i,j=jobs[n];c=cc[i];rows,cpu=energy.block(a.capture/c['file'],j,c['first']);converted=[dict(r,sample_4msps=(r['ticks']-c['first']*5)//3) for r in rows];energy_rows[i]+=rows
     low.offer_completion(SimpleNamespace(epoch=epoch,first=c['first']),converted,dict(worker_role='dsp',block_range=(j,j+1),cpu_method_energy_s=cpu));n+=1
    low.tick()
    for f in sorted((root/'feed-outbox').glob('*.json')):
     x=json.loads(f.read_text());assert x['epoch']==epoch and x['alignment']['verified'] and x['alignment']['matches']>=20 and x['alignment']['median_abs_error_us']<=2
     emitted+=x['extra'];f.unlink()
    if low.epoch is not None:
     for c in cc:
      key=c['first'];w=low.bridge.windows.get(key)
      if key not in closed and w and w['finalized']:closed[key]=low.stream_rows(key,epoch)
    if n==len(jobs) and k==len(iq)//2 and low.count['native_seconds']==len(cc) and len(closed)==len(cc):break
    time.sleep(.001)
   assert len(emitted)==79,low.report();assert low.count['shared_energy_blocks']==168;assert not low.failed
   by={r['source']:sum(x['source']==r['source'] for x in emitted) for r in emitted};assert by=={'energy':32,'stream1090':47},by
   expected=[]
   for i,c in enumerate(cc):
    sr,cpu=closed[c['first']];assert sr is not None and cpu>0
    lo=(c['first']+600)*5;hi=lo+12000000;o,audit,_=evaluate(known.snapshot(),[r for r in energy_rows[i] if lo<=r['ticks']<hi]+sr,lo,hi);assert audit['verified'];expected += [r for r in o if lo<=r['ticks']<hi]
   def match(r,rows):return any(r['message_hex']==x['message_hex'] and abs(r['ticks']-x['ticks'])<=1440 for x in rows)
   assert len(expected)==79 and all(match(r,emitted) for r in expected)
   recorded=[r for b in d['base'] for r in b['extra']];assert all(match(r,recorded) for r in emitted)
   # Combined membership: early rows plus unchanged grouped other-method rows.
   union=emitted+[r for r in recorded if not match(r,emitted)];assert len(union)==len(recorded)==210 and all(match(r,union) for r in recorded)
   report=low.report();old=cc[-1]['first']+CORE;assert old in low.windows and not low.bridge.windows[old]['finalized'];assert low.begin(old+5*CORE) and low.count['retired_incomplete_early_windows']>=1 and not low.begin(old) and low.stream_rows(old,epoch)[0] is None
   config.write_text('{"enabled":false}');low.last_cfg=0.;low.tick();assert low.failed and low.stream_rows(first,epoch)[0] is None
  finally:low.close()
 # A fast completion cannot disappear during ordered pool consumption.
 q=concurrent.futures.Future();q.set_result(([],{'worker_role':'dsp','block_range':(0,1)}))
 class Pool:
  def __init__(self):self.pending=[('batch',[q],0,None)]
  def pop(self):self.pending.clear();return 'group'
 tap=CompletionTap(Pool());assert tap.pop()=='group' and len(tap.take())==1;tap.pop();assert not tap.take()
 report=dict(report,all_passed=True,retained=79,recorded_union=210,source_counts=by,fall_back_on_disabled_config=True,complete_tap_once=True,incomplete_window_retires=True,production_actions=[])
 a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':main()

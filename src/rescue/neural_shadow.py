"""Opt-in paired neural comparison on mirrored batches. NO feeder output."""
import argparse,hashlib,json,signal,threading,time
from collections import Counter,deque
from pathlib import Path
from .neural_spool import Spool
from .streaming import StreamingPool,HALO,CORE,RATE
from .workers import merge_events,plan
from .shadow import LiveInput,evaluate
from .telemetry import Archive,BINS,distance_bin

class PairedStreamingPool(StreamingPool):
    def combine_events(self,parts):
        rows=[r for part in parts for r in part]
        # Preserve frozen predictions even when RF predicts the same transmission
        # from an earlier overlapping candidate window or neighbouring block.
        return merge_events([[r for r in rows if r.get('model_origin')!='rf_companion'],
                             [r for r in rows if r.get('model_origin')=='rf_companion']])

def incremental_neural(extras,base):
    added=[];duplicates=[]
    for r in extras:
        if r['source']!='neural':continue
        if any(b['message_hex']==r['message_hex'] and abs(b['ticks']-r['ticks'])<=1440 for b in base):duplicates.append(r)
        else:added.append(r)
    return added,duplicates

class NeuralStats:
    def __init__(self):self.total=Counter();self.bins={b:Counter() for b in BINS}
    def record(self,kind,distance):self.total[kind]+=1;self.bins[distance_bin(distance)][kind]+=1
    def report(self):return dict(total=dict(self.total),bins_nm={k:dict(v) for k,v in self.bins.items()},denominator='Only RF seconds decoded by both pipelines with verified stock clock alignment; prior stock-only positions <=15 s')

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--companion',type=Path);p.add_argument('--companion-sha256');p.add_argument('--workers',type=Path,required=True);p.add_argument('--spool',type=Path,default=Path('/run/adsb-rescue/neural'));p.add_argument('--runtime',type=Path,default=Path('/run/adsb-neural-rescue'));p.add_argument('--archive',type=Path,default=Path('/var/lib/adsb-neural-rescue'));p.add_argument('--lat',type=float,required=True);p.add_argument('--lon',type=float,required=True);a=p.parse_args()
    a.runtime.mkdir(parents=True,exist_ok=True)
    original=a.root/'models/tiny-fp32.onnx';companion=a.companion or a.root/'models/candidates/tiny-rf-blend.onnx'
    hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in (('frozen',original),('rf_companion',companion))}
    if hashes['rf_companion']!=(a.companion_sha256 or '139875cd05c8d3ffc1eb8fd64a268bf97ed88b5e99b52ad7007b34a545136bec'):raise ValueError('Unexpected RF companion model')
    methods=dict(energy=True,neural=True,crc=False,timing=False,soft=False,matched=False,coherent=False,header=False,sic=False)
    pool=PairedStreamingPool(original,methods,a.runtime,plan(a.workers),companion=companion)
    live=LiveInput(a.runtime/'unused-iq.sock',(a.lat,a.lon));live.start(include_iq=False)
    spool=Spool(a.spool);archive=Archive(a.archive,ram_limit=32*1024**2,disk_limit=256*1024**2,lock_memory=True)
    counts=Counter();stats=NeuralStats();waiting=deque();stop=threading.Event();started=time.time();last_status=0;last_heartbeat=0;quota=Counter();minute=None;alignment={}
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
    def status():
        _,health=live.snapshot()
        return dict(mode='paired_neural_shadow_no_forwarding',forwarding_enabled=False,started_unix=started,updated_unix=time.time(),model_sha256=hashes,workers=pool.report(),counts=dict(counts),distance=stats.report(),input=dict(spool.count),alignment=alignment,health=health,archive=archive.report(),threads_alive=all(t.is_alive() for t in live.threads),comparison='Neural output minus stock DF17 and accepted energy/timing/soft/matched/coherent DSP transmissions, same payload within 120 us',selection='Frozen predictions win; RF companion rescues failed frozen windows only',waiting_for_dsp=len(waiting))
    try:
        while not stop.is_set():
            now=time.time()
            if now-last_heartbeat>=1:spool.heartbeat();last_heartbeat=now
            if len(pool.pending)<pool.max_pending_jobs:
                batch=spool.take()
                if batch:
                    if time.monotonic()-batch.queued>3:counts['stale_batches_shed']+=1
                    else:pool.submit(batch)
            result=pool.pop()
            if result:
                if len(waiting)>=3:waiting.popleft();counts['comparison_backlog_shed']+=1
                waiting.append((time.monotonic(),result))
            if waiting:
                received,(item,events,work)=waiting[0];epoch,first,wall,raw,queued=item
                base=spool.base(epoch,first)
                if base is None:
                    if time.monotonic()-received>5:waiting.popleft();counts['missing_dsp_window']+=1
                else:
                    waiting.popleft()
                    if not base['alignment']['verified']:counts['unaligned_dsp_window']+=1;continue
                    frames,health=live.snapshot()
                    if time.time()-health.get('aircraft_unix',0)>5:counts['unhealthy_seconds']+=1;continue
                    start=(first+HALO)*5;end=start+12000000
                    if (base['start'],base['end'])!=(start,end):raise ValueError('Comparison sample clocks differ')
                    candidates=[{**e,'ticks':first*5+e['sample_4msps']*3} for e in events if HALO*5//3<=e['sample_4msps']<(HALO+CORE)*5//3]
                    extras,alignment,decisions=evaluate(frames,candidates,start,end)
                    if not alignment['verified']:counts['unaligned_neural_seconds']+=1;continue
                    counts['compared_rf_seconds']+=1;counts['inference_windows']+=work['neural_windows'];counts['late_blocks']+=work['late_blocks']
                    added,duplicates=incremental_neural(extras,base['extra'])
                    counts['neural_vs_stock']+=len(added)+len(duplicates);counts['already_recovered_by_dsp']+=len(duplicates);counts['total_neural_on_top']+=len(added)
                    for f in [f for f in frames if start<=f['ticks']<end]:
                        d,_=live.distance(f['message_hex'],wall+(f['ticks']-first*5)/12e6);stats.record('stock_df17',d)
                    for f in base['extra']:
                        d,_=live.distance(f['message_hex'],wall+(f['ticks']-first*5)/12e6);stats.record('dsp_extra',d)
                    this_minute=int(wall//60)
                    if minute!=this_minute:quota.clear();minute=this_minute
                    for r in added:
                        origin=r.get('model_origin','frozen');counts[origin+'_on_top']+=1
                        unix=wall+(r['ticks']-first*5)/12e6;d,age=live.distance(r['message_hex'],unix);stats.record(origin+'_extra',d)
                        archive.add(dict(record='neural_on_top',epoch=epoch,unix=unix,distance_nm=d,position_age_s=age,training_eligible=False,model_sha256=hashes,**r))
                        if quota[origin]<10:
                            sample=round((r['ticks']-first*5)/5);lo=sample-2400;hi=sample+2400
                            if lo>=0 and hi<=len(raw)//2:
                                archive.add(dict(record='training_window',label_provenance=origin+'_candidate_unverified',training_eligible=False,target_hex=r['message_hex'],epoch=epoch,unix=wall+lo/RATE,sample_start=first+lo,event_sample_in_window=sample-lo,sample_rate=RATE,format='uc8',distance_nm=d,position_age_s=age,gain_db=health.get('gain_db'),model_sha256=hashes,stock_context=[dict(ticks=f['ticks'],message_hex=f['message_hex'],signal_byte=f['signal_byte']) for f in frames if abs(f['ticks']-r['ticks'])<12000]),raw[lo*2:hi*2]);quota[origin]+=1
                    archive.add(dict(record='neural_window_health',epoch=epoch,sample_start=first,unix=wall,alignment=alignment,work=work,neural_on_top=len(added),already_dsp=len(duplicates),base_dsp_extras=len(base['extra']),decisions=decisions))
            if now-last_status>=10:
                report=status();tmp=a.runtime/'status.tmp';tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(a.runtime/'status.json');archive.flush(report);last_status=now
            stop.wait(.003)
    finally:
        (spool.path/'enabled').unlink(missing_ok=True);live.close();pool.close();archive.flush(status(),force=True)
if __name__=='__main__':main()

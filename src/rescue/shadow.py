"""Bounded live rescue + training collection. No SDR ownership.

Only the existing readsb SDR callback sends copied UC8 into this Unix datagram
socket. Congestion loses experimental work, never backpressures readsb.
"""
import argparse,bisect,hashlib,json,os,queue,signal,socket,struct,threading,time
from collections import Counter,defaultdict,deque
from functools import lru_cache
from pathlib import Path
import numpy as np
from .wire import BeastParser
from .far_capture import CaptureClient
from .method_metrics import MethodMetrics
from .crc_verification import CrcVerifier
from .stock_history import StockHistory,StockSnapshot,has_prior,has_conflict
from .telemetry import Archive,DistanceStats,distance_nm
from .streaming import RATE,CORE,HALO,Assembler,StreamingPool,make_streaming_pool
HEADER=struct.Struct('<4sIIIQQQ')
CORRECTION_TICKS=2398 # pinned readsb 3.16.17: 64us + 326/2.4M history
@lru_cache(maxsize=20000)
def valid_df17(payload):
    if len(payload)!=28:return False
    try:value=int(payload,16)
    except ValueError:return False
    if value>>107!=17:return False
    for bit in range(111,23,-1):
        if value&(1<<bit):value^=0x1fff409<<(bit-24)
    return value==0
class LiveInput:
    def __init__(self,sockpath,origin,dispatch_ms=100,indexed_stock_history=False):
        self.path=Path(sockpath);self.origin=origin;self.stop=threading.Event();self.queue=queue.Queue(2000//dispatch_ms);self.dispatch_ms=dispatch_ms
        self.capture=CaptureClient();self.count=Counter();self.frames=StockHistory() if indexed_stock_history else deque(maxlen=100000);self.positions=defaultdict(lambda:deque(maxlen=40));self.lock=threading.Lock();self.health={};self.threads=[]
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.unlink(missing_ok=True)
        self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1024*1024)
        self.socket.bind(str(self.path));os.chmod(self.path,0o660);self.socket.settimeout(1)
    def start(self,include_iq=True):
        for method in ((self.iq,self.stock,self.context) if include_iq else (self.stock,self.context)):
            t=threading.Thread(target=method,daemon=True);t.start();self.threads.append(t)
    def iq(self):
        assembler=Assembler(self.dispatch_ms);epoch=None;last_dropped=0
        while not self.stop.is_set():
            try:packet=self.socket.recv(60100)
            except socket.timeout:continue
            except OSError:break
            if len(packet)<HEADER.size:self.count['bad_datagram']+=1;continue
            magic,pid,rate,n,sample,ns,dropped=HEADER.unpack_from(packet)
            if magic!=b'RSC1' or rate!=RATE or n%2 or n!=len(packet)-HEADER.size:self.count['bad_datagram']+=1;continue
            if epoch is None or pid!=epoch:
                self.count['tap_dropped_before_connection']+=dropped;last_dropped=dropped
            self.count['tap_dropped_samples']+=max(0,dropped-last_dropped);last_dropped=dropped
            epoch=pid
            self.capture.send(packet)
            before=assembler.discontinuities
            batches=assembler.feed(pid,sample,ns/1e9,packet[HEADER.size:])
            self.count['iq_discontinuities']+=assembler.discontinuities-before
            for batch in batches:
                try:self.queue.put_nowait(batch)
                except queue.Full:
                    try:self.queue.get_nowait();self.count['queue_shed_batches']+=1;self.count['queue_shed_seconds']+=self.dispatch_ms/1000
                    except queue.Empty:pass
                    try:self.queue.put_nowait(batch)
                    except queue.Full:self.count['queue_shed_batches']+=1;self.count['queue_shed_seconds']+=self.dispatch_ms/1000
    def stock(self):
        while not self.stop.is_set():
            try:
                with socket.create_connection(('127.0.0.1',30005),timeout=2) as sock:
                    self.count['stock_connections']+=1;sock.settimeout(1);parser=BeastParser()
                    while not self.stop.is_set():
                        try:data=sock.recv(65536)
                        except socket.timeout:continue
                        if not data:break
                        now=time.time();frames=parser.feed(data)
                        with self.lock:
                            for frame in frames:
                                if not valid_df17(frame['message_hex']):continue
                                self.frames.append({**frame,'ticks':frame['ticks_12mhz']-CORRECTION_TICKS,'arrival':now})
                            while self.frames and now-self.frames[0]['arrival']>40:self.frames.popleft()
            except (OSError,ValueError):self.count['stock_disconnects']+=1
            self.stop.wait(1)
    def context(self):
        while not self.stop.is_set():
            try:
                aircraft=json.loads(Path('/run/readsb/aircraft.json').read_text());stats=json.loads(Path('/run/readsb/stats.json').read_text());now=aircraft['now']
                with self.lock:
                    self.health={'aircraft_unix':now,'gain_db':stats.get('gain_db'),'local':stats.get('total',{}).get('local',{})}
                    for a in aircraft['aircraft']:
                        if not all(k in a for k in ('lat','lon','seen_pos')) or a.get('hex','').startswith('~'):continue
                        stamp=now-a['seen_pos'];h=a['hex'].lower();history=self.positions[h]
                        if not history or stamp>history[-1][0]:history.append((stamp,distance_nm(a['lat'],a['lon'],self.origin)))
                    for h in list(self.positions):
                        if self.positions[h] and now-self.positions[h][-1][0]>60:del self.positions[h]
            except (OSError,ValueError,KeyError):self.count['context_errors']+=1
            self.stop.wait(1)
    def distance(self,payload,unix):
        with self.lock:
            history=self.positions.get(payload[2:8],())
            for stamp,distance in reversed(history):
                if 0<=unix-stamp<=15:return distance,unix-stamp
        return None,None
    def snapshot(self):
        with self.lock:return (self.frames.snapshot() if isinstance(self.frames,StockHistory) else list(self.frames)),dict(self.health)
    def close(self):
        self.stop.set();self.socket.close()
        for thread in self.threads:thread.join(timeout=3)
        self.path.unlink(missing_ok=True);self.capture.close()

def evaluate(frames,candidates,start,stop):
    """Sample-clock matching; stock-only identity, conservative 120us dedupe.
    Primary is never altered. Same payload at different transmission times counts.
    """
    candidates=[r for r in candidates if r["source"] in ("energy","timing","soft","matched","coherent","sequence","acquisition","pulse","header","sic","neural")]
    indexed=isinstance(frames,StockSnapshot)
    payloads=dict(frames.payloads) if indexed else defaultdict(list)
    identities=frames.identities if indexed else defaultdict(list)
    copied=set()
    for r in (() if indexed else frames):
        t=r['ticks'];p=r['message_hex'];payloads[p].append(t);identities[p[2:8]].append((t,p))
    if not indexed:
        for times in payloads.values():times.sort()
        for rows in identities.values():rows.sort()
    errors=[]
    for r in candidates:
        if r['source']!='energy':continue
        times=payloads.get(r['message_hex'],[]);i=bisect.bisect_left(times,r['ticks'])
        nearest=times[max(0,i-1):i+1]
        if nearest:
            error=min(abs(t-r['ticks']) for t in nearest)
            if error<12000:errors.append(error)
    median=float(np.median(errors)) if errors else None
    audit={'matches':len(errors),'median_abs_error_us':None if median is None else median/12,'verified':len(errors)>=20 and median<=24}
    energy=defaultdict(list)
    for r in candidates:
        if r['source']=='energy' and valid_df17(r['message_hex']):energy[r['message_hex']].append(r['ticks'])
    for times in energy.values():times.sort()
    extra=[];decisions=Counter()
    if not audit['verified']:return [],audit,{'alignment_unverified':len(candidates)}
    for r in sorted(candidates,key=lambda r:((('energy','timing','soft','matched','coherent','sequence','acquisition','pulse','header','sic','neural').index(r['source'])),r['ticks'])):
        t=r['ticks'];p=r['message_hex'];times=payloads.get(p,[])
        if not valid_df17(p):decisions['invalid']+=1;continue
        if r['source']=='neural':
            known=energy.get(p,[]);j=bisect.bisect_left(known,t-1440)
            if j<len(known) and known[j]<=t+1440:decisions['neural_duplicate_energy']+=1;continue
        i=bisect.bisect_left(times,t-1440)
        if i<len(times) and times[i]<=t+1440:decisions['duplicate_120us']+=1;continue
        rows=identities.get(p[2:8],())
        previous=has_prior(rows,t) if indexed else [(s,q) for s,q in rows if t-360000000<=s<=t]
        if not previous:decisions['no_prior_stock_icao']+=1;continue
        conflict=has_conflict(rows,t,p) if indexed else any(abs(s-t)<=48 and q!=p for s,q in rows)
        if conflict:decisions['stock_conflict']+=1;continue
        if indexed and p not in copied:
            payloads[p]=list(times);copied.add(p)
        extra.append(r);bisect.insort(payloads[p],t);decisions['added_'+r['source']]+=1
    return extra,audit,dict(decisions)

def evaluate_crc_research(frames,candidates,accepted,alignment):
    """Count guarded CRC repairs separately; never return feeder candidates."""
    decisions=Counter()
    if not alignment.get('verified'):
        return [],{'unaligned':len(candidates)}
    wanted={r['message_hex'][2:8] for r in candidates if len(r.get('message_hex',''))==28}
    indexed=isinstance(frames,StockSnapshot)
    stock=defaultdict(list)
    payloads=defaultdict(list)
    if indexed:
        for icao in wanted:
            stock[icao]=list(frames.identities.get(icao,()))
        for r in candidates:
            payloads[r['message_hex']]=list(frames.payloads.get(r['message_hex'],()))
    else:
        for f in frames:
            p=f['message_hex']
            if p[2:8] in wanted:
                stock[p[2:8]].append((f['ticks'],p))
                payloads[p].append(f['ticks'])
        for rows in stock.values():rows.sort()
        for times in payloads.values():times.sort()
    other=defaultdict(list)
    for r in accepted:
        if r['message_hex'][2:8] in wanted:
            bisect.insort(payloads[r['message_hex']],r['ticks'])
            bisect.insort(other[r['message_hex'][2:8]],(r['ticks'],r['message_hex']))
    extras=[]
    for r in sorted(candidates,key=lambda row:row['ticks']):
        p=r['message_hex'];t=r['ticks'];icao=p[2:8]
        if not valid_df17(p):decisions['invalid']+=1;continue
        times=payloads[p];i=bisect.bisect_left(times,t-1440)
        if i<len(times) and times[i]<=t+1440:decisions['duplicate']+=1;continue
        rows=stock[icao]
        if not has_prior(rows,t):decisions['no_prior_stock_icao']+=1;continue
        if has_conflict(rows,t,p) or has_conflict(other[icao],t,p):decisions['conflict']+=1;continue
        extras.append(r);bisect.insort(times,t);bisect.insort(other[icao],(t,p))
        decisions['guarded']+=1
    return extras,dict(decisions)

def main():
    p=argparse.ArgumentParser();p.add_argument('--cpu-budget-config',type=Path,help='Opt-in total CPU governor; rescue-only admission, never stock throttling');p.add_argument('--no-logging',action='store_true',help='Disable experimental archives and IQ/training collection; retain live statistics and feeding');p.add_argument('--crc-verification',action='store_true',help='Collect bounded, research-only Broad CRC RF evidence in a separate 12-hour archive');p.add_argument('--indexed-stock-history',action='store_true',help='Experimental coordinator index; default off');p.add_argument('--neural-spool',type=Path);p.add_argument('--dispatch-ms',type=int,choices=(50,100),default=100);p.add_argument('--config',type=Path);p.add_argument('--worker-config',type=Path);p.add_argument('--root',type=Path,required=True);p.add_argument('--broad-crc-shadow',action='store_true',help='Quarantine CRC repairs; never count as accepted extras');p.add_argument('--runtime',type=Path,default=Path('/run/adsb-rescue'));p.add_argument('--archive',type=Path,default=Path('/var/lib/adsb-rescue'));p.add_argument('--lat',type=float,required=True);p.add_argument('--lon',type=float,required=True);a=p.parse_args()
    a.runtime.mkdir(parents=True,exist_ok=True);model=a.root/'models/tiny-fp32.onnx'
    from deadsb.governor import Governor,Config,read_cpu
    governor=Governor(Config.from_dict(json.loads(a.cpu_budget_config.read_text()))) if a.cpu_budget_config else None
    budget_sampled=0.;budget_rf=None
    from .pipeline import settings
    methods=settings(a.config)
    a.broad_crc_shadow=methods['crc']
    from .workers import plan
    selection=plan(a.worker_config)
    coherent_settings={k:selection['config']['coherent_'+k] for k in ('threshold','budget')}
    pool=make_streaming_pool(model,methods,a.runtime,selection,dispatch_ms=a.dispatch_ms)
    from .neural_spool import Spool
    spool=Spool(a.neural_spool) if a.neural_spool else None
    live=LiveInput(a.runtime/'iq.sock',(a.lat,a.lon),dispatch_ms=a.dispatch_ms,indexed_stock_history=a.indexed_stock_history);archive=Archive(a.archive,lock_memory=True,enabled=not a.no_logging);stats=DistanceStats();metrics=MethodMetrics();counts=Counter();crc_recent=deque(maxlen=512);started=time.time();last_status=0;last_sample_minute=None;quota=Counter();timing=deque(maxlen=600);alignment={};last_epoch=None
    from .training_collection import DatasetCollector
    training_collector=DatasetCollector(archive)
    crc_verifier=CrcVerifier(a.archive/'crc-verification') if methods['crc'] and a.crc_verification else None
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
    live.start();modelsha=hashlib.sha256(model.read_bytes()).hexdigest()
    def status():
        _,health=live.snapshot()
        return {'cpu_budget':governor.report() if governor else {'enabled':False},'method_metrics':metrics.report(stats.report()['total']),'capture_transport':dict(live.capture.count),'method_switches':{**methods,'sequence':selection['config']['sequence_acquisition'] and selection['config']['sequence_enabled'],'acquisition':selection['config']['sequence_acquisition'] and selection['config']['acquisition_enabled']},'logging_enabled':not a.no_logging,'indexed_stock_history':a.indexed_stock_history,'mode':'feeding_validated_dsp' if (a.runtime/'feed-routing.json').exists() else 'dsp_candidate_collection','pipeline_methods':methods,'coherent_settings':coherent_settings,'forwarding_enabled':(a.runtime/'feed-routing.json').exists(),'workers':pool.report(),'neural_mirror':dict(spool.count) if spool else None,'broad_crc_mode':'quarantine_only' if a.broad_crc_shadow else 'off','crc_research_recent':list(crc_recent),'crc_verification':crc_verifier.report() if crc_verifier else None,'crc_research_policy':'Aligned, CRC-valid, prior-stock ICAO, no stock/accepted duplicate or conflict; research only, never routed to FR24','started_unix':started,'updated_unix':time.time(),'model_sha256':modelsha,'position_provenance':'stock-only prior position, age <=15 seconds; unknown kept separate','counts':dict(counts),'input':dict(live.count),'distance':stats.report(),'archive':archive.report(),'training_collection':{**training_collector.report(),'enabled':not a.no_logging},'alignment':alignment,'health':health,'mean_processing_s':sum(timing)/len(timing) if timing else None,'max_recent_processing_s':max(timing,default=None),'threads_alive':all(t.is_alive() for t in live.threads)}
    try:
        while not stop.is_set():
            if governor and time.monotonic()-budget_sampled>=1:
                budget_sampled=time.monotonic()
                try:
                    governor.config=Config.from_dict(json.loads(a.cpu_budget_config.read_text()))
                    total,idle=read_cpu()
                    try:temperature=int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000
                    except OSError:temperature=None
                    governor.observe(total,idle,temperature=temperature,backlog=live.queue.qsize()>15)
                except (OSError,ValueError,TypeError):governor.fail('telemetry_or_config_error')
            # A bounded number of small batches; whole-second comparisons are
            # assembled only after DSP, with a separate stock settling delay.
            if len(pool.pending)<pool.max_pending_jobs:
                try:item=live.queue.get(timeout=.005)
                except queue.Empty:item=None
                if item:
                    epoch,first,wall,queued=item.epoch,item.first,item.wall,item.queued
                    if time.monotonic()-queued>3:
                        counts['stale_batches_shed']+=1;counts['stale_seconds_shed']+=a.dispatch_ms/1000
                    else:
                        references=()
                        if methods['sic']:
                            frames,_=live.snapshot()
                            references=[{**f,'seconds':(f['ticks']-first*5)/12e6} for f in frames]
                        if governor and budget_rf!=(epoch,first):
                            budget_rf=(epoch,first);pool.job_policy=governor.policy()
                        pool.submit(item,references)
                        if spool:spool.publish(item)
            result=pool.pop()
            if result:
                item,events,work=result
                metrics.record(work)
                epoch,first,wall,raw,queued=item
                if time.monotonic()-queued>5:counts['stale_results_shed']+=1;continue
                if epoch!=last_epoch:counts['receiver_epochs']+=1;last_epoch=epoch
                timing.append(work['job_wall_s'])
                counts['processed_seconds']+=1;counts['neural_windows']+=work['neural_windows'];counts['budget_dropped']+=work['budget_dropped'];counts['late_blocks']+=work['late_blocks']
                candidates=[{**e,'ticks':first*5+e['sample_4msps']*3} for e in events if HALO*5//3<=e['sample_4msps']<(HALO+CORE)*5//3]
                frames,health=live.snapshot();start=(first+HALO)*5;end=start+12000000
                if crc_verifier:crc_verifier.settle(frames,epoch,wall)
                if time.time()-health.get('aircraft_unix',0)>5:counts['unhealthy_seconds']+=1;continue
                corrected=[r for r in candidates if r['source']=='broad_crc']
                candidates=[r for r in candidates if r['source']!='broad_crc']
                counts['crc_quarantined_raw']+=len(corrected)
                extra,alignment,decisions=evaluate(frames,candidates,start,end);counts.update(decisions)
                crc_extra,crc_decisions=evaluate_crc_research(frames,corrected,extra,alignment)
                counts.update({'crc_research_'+k:v for k,v in crc_decisions.items()})
                crc_ids={id(r) for r in crc_extra}
                if spool:spool.publish_base(epoch,first,{'epoch':epoch,'first':first,'start':start,'end':end,'alignment':alignment,'extra':extra,'methods':methods,'coherent_settings':coherent_settings})
                if not alignment['verified']:counts['unaligned_seconds']+=1;continue
                counts['aligned_seconds']+=1
                live.capture.frames(epoch,[dict(r,unix=wall+(r['ticks']-first*5)/12e6) for r in extra])
                # Optional relay consumes only already-validated, aligned cheap DSP
                # extras. Bounded RAM outbox never blocks the receiver or workers.
                outbox=a.runtime/'feed-outbox'
                if outbox.is_dir():
                    files=sorted(outbox.glob('*.json'))
                    for old in files[:-15]:old.unlink(missing_ok=True)
                    tmp=outbox/'batch.tmp'
                    tmp.write_text(json.dumps({'created_unix':time.time(),'epoch':epoch,'alignment':alignment,'extra':extra}))
                    tmp.replace(outbox/(str(epoch)+'-'+str(first)+'.json'))
                primary=[f for f in frames if start<=f['ticks']<end]
                for f in primary:
                    d,age=live.distance(f['message_hex'],wall+(f['ticks']-first*5)/12e6);stats.record('stock_df17',d)
                minute=int(wall//60)
                if minute!=last_sample_minute:quota.clear();last_sample_minute=minute
                # Snippets are centered using the shared SDR sample clock. Labels
                # from neural candidates remain quarantined, never auto-training.
                samples=[]
                stock_times=defaultdict(list)
                if not isinstance(frames,StockSnapshot):
                    for f in frames:stock_times[f['message_hex'][2:8]].append(f['ticks'])
                    for times in stock_times.values():times.sort()
                for r in corrected:
                    unix=wall+(r['ticks']-first*5)/12e6;d,age=live.distance(r['message_hex'],unix)
                    if isinstance(frames,StockSnapshot):
                        prior=has_prior(frames.identities.get(r['message_hex'][2:8],()),r['ticks'])
                    else:
                        times=stock_times.get(r['message_hex'][2:8],[]);idx=bisect.bisect_right(times,r['ticks'])
                        prior=idx>0 and times[idx-1]>=r['ticks']-360000000
                    counts['crc_quarantined_prior_stock' if prior else 'crc_quarantined_unknown_address']+=1
                    research_extra=id(r) in crc_ids
                    if research_extra:
                        stats.record('crc_research_extra',d)
                        crc_recent.append({'unix':unix,'icao':r['message_hex'][2:8],'distance_nm':d,'position_age_s':age,'message_hex':r['message_hex'],'flipped_bits':r.get('flipped_bits',[]),'flip_confidences':r.get('flip_confidences',[]),'preamble_score':r.get('preamble_score')})
                        if crc_verifier:crc_verifier.collect(r,raw,epoch,first,wall,d,age,health.get('gain_db'))
                    archive.add({'record':'crc_quarantine','unix':unix,'epoch':epoch,'distance_nm':d,'position_age_s':age,
                        'gain_db':health.get('gain_db'),'prior_stock_address':prior,'research_extra':research_extra,'training_eligible':False,**r})
                    if quota['crc_candidate_unverified']<10:samples.append((r,'crc_candidate_unverified'))
                for r in extra:
                    unix=wall+(r['ticks']-first*5)/12e6;d,age=live.distance(r['message_hex'],unix);stats.record(r['source']+'_extra',d)
                    archive.add({'record':'extra','unix':unix,'distance_nm':d,'position_age_s':age,'epoch':epoch,**r})
                    samples.append((r,r['source']+'_candidate_unverified'))
                # New sampler owns waveform selection, quotas and provenance.
                # Legacy metadata records above remain; no duplicate IQ sampler.
                if not a.no_logging:training_collector.collect(raw,epoch,first,wall,primary,frames,extra,corrected,health,live.distance)
                archive.add({'record':'window_health','unix':wall,'epoch':epoch,'sample_start':first,'processing_s':timing[-1],'work':work,'alignment':alignment,'stock_df17':len(primary),'decisions':decisions,'health':health})
            if not result:stop.wait(.002)
            if time.time()-last_status>=10:
                report=status();temp=a.runtime/'status.tmp';temp.write_text(json.dumps(report,indent=2)+'\n');temp.replace(a.runtime/'status.json');last_status=time.time();archive.flush(report)
                if crc_verifier:crc_verifier.flush()
    finally:
        live.close();pool.close();archive.flush(status(),force=True)
        if crc_verifier:crc_verifier.close()
if __name__=='__main__':main()

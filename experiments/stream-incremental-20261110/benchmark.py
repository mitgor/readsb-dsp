"""Frozen RF, exact raw publication and guard retention, paced decoder latency."""
import argparse,json,hashlib,time,statistics,collections,platform,resource
from pathlib import Path
from bindings import Decoder
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--batch',type=Path,required=True);p.add_argument('--incremental',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--repeat',type=int,default=1);p.add_argument('--paced-windows',type=int,default=8);a=p.parse_args();assert not a.output.exists();P=a.root/'prepared';cases=[c for c in json.loads((P/'cases.json').read_text()) if c['reference_coverage_complete']];d=Decoder(a.batch,a.incremental);modes=['batch','20ms','50ms'];events={m:[] for m in modes};cost=collections.defaultdict(collections.Counter);details=[];RATE=2400000

def incremental(raw,c,ms):
    ctx=d.begin(c['first_sample'],len(raw)//2);rows=[]
    try:
        step=RATE*ms//1000
        for at in range(0,len(raw)//2,step):rows+=d.feed(ctx,raw[2*at:2*(at+step)],c['first_sample']+at)
        rows+=d.finish(ctx);return rows
    finally:d.close(ctx)
def canonical(rows,c):
    # Pin the same physical RF preamble origin as the corrected parent study.
    out=[];seen={}
    for t,m in sorted(rows):
        if m in seen and t-seen[m]<=1440:continue
        seen[m]=t;wire=t+769;rf=wire-2400
        if c['core_start']*5<=rf<c['core_end']*5:out.append((c['id'],wire,m))
    return out
with (P/'rf.bin').open('rb') as rf:
 for i,c in enumerate(cases):
    rf.seek(c['byte_offset']);raw=rf.read(c['bytes']);assert hashlib.sha256(raw).hexdigest()==c['sha256'];outputs={};order=modes[(i+a.repeat)%3:]+modes[:(i+a.repeat)%3];row={'case':c['id'],'family':c['family'],'cpu':{}}
    for mode in order:
        cpu=time.process_time();wall=time.monotonic();rows=d.whole(raw,c['first_sample']) if mode=='batch' else incremental(raw,c,int(mode[:-2]));elapsed=time.process_time()-cpu
        cost[c['family']+'_'+mode]['cpu_s']+=elapsed;cost[c['family']+'_'+mode]['wall_s']+=time.monotonic()-wall;row['cpu'][mode]=elapsed;outputs[mode]=rows;events[mode]+=canonical(rows,c)
    assert outputs['batch']==outputs['20ms']==outputs['50ms'],(c['id'],'RAW packet/timestamp/order mismatch')
    details.append(row)
    if i%50==0:print('Exact chunk parity',i+1,'/',len(cases),flush=True)
# Validate retained stock extras and full current-pipeline comparisons using the
# frozen parent's complete reference masks, not future data as early admission.
parent=json.loads((a.root/'reference-result.json').read_text());digest=lambda rows:hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest()
for mode in modes:assert digest(events[mode])==parent['digests']['raw_native'],(mode,'Parent physical-core digest mismatch')
families={}
for family in ['long','recent']:
    cc=[c for c in cases if c['family']==family];seconds=sum(c['core_end']-c['core_start'] for c in cc)/RATE;families[family]={'windows':len(cc),'core_rf_seconds':seconds,'cpu':{m:{**dict(cost[family+'_'+m]),'cpu_s_per_rf_s':cost[family+'_'+m]['cpu_s']/seconds} for m in modes},'retained_reference_counts':parent['families'][family]['counts'],'retained_distance_bins':parent['families'][family]['distance_bins']}
# Real-time-paced replay: each method alone, identical frozen windows. Times
# are decoder output availability AFTER the packet's RF end, excluding stock
# admission, tap transport, scheduling outside this isolated consumer and FR24.
long=[c for c in cases if c['family']=='long'];chosen=[long[round(i*(len(long)-1)/max(1,a.paced_windows-1))] for i in range(a.paced_windows)] if a.paced_windows else [];lat=collections.defaultdict(list);lat_rows={};paced_cpu=collections.Counter();finishes=collections.Counter();alignment_offset=1631
with (P/'rf.bin').open('rb') as rf:
 for c in chosen:
    rf.seek(c['byte_offset']);raw=rf.read(c['bytes']);per={}
    for mode in modes:
        rows=[];available=[];base=time.monotonic();cpu=0.;ctx=None
        if mode!='batch':
            t=time.process_time();ctx=d.begin(c['first_sample'],len(raw)//2);cpu+=time.process_time()-t
        try:
            step=len(raw)//2 if mode=='batch' else RATE*int(mode[:-2])//1000
            for at in range(0,len(raw)//2,step):
                stop=min(at+step,len(raw)//2);due=base+stop/RATE;wait=due-time.monotonic()
                if wait>0:time.sleep(wait)
                t=time.process_time();new=d.whole(raw,c['first_sample']) if mode=='batch' else d.feed(ctx,raw[2*at:2*stop],c['first_sample']+at);cpu+=time.process_time()-t;stamp=time.monotonic()-base
                rows+=new;available += [stamp]*len(new)
            if ctx:
                t=time.process_time();new=d.finish(ctx);cpu+=time.process_time()-t;stamp=time.monotonic()-base;rows+=new;available += [stamp]*len(new);finishes[mode]+=len(new)
        finally:
            if ctx:
                t=time.process_time();d.close(ctx);cpu+=time.process_time()-t
        paced_cpu[mode]+=cpu;per[mode]=rows
        for (ticks,msg),stamp in zip(rows,available):
            physical=(ticks-c['first_sample']*5-alignment_offset)/12000000
            if (c['core_start']-c['first_sample'])/RATE<=physical<(c['core_end']-c['first_sample'])/RATE:
                delay=(stamp-(physical+.000120))*1000;assert delay>=-1,'Output before RF packet end';lat[mode].append(delay)
        lat_rows[c['id'],mode]=len(rows)
    assert per['batch']==per['20ms']==per['50ms'],c['id']
    print('Paced window complete',c['id'],flush=True)
def stats(v):
    if not v:return None
    v=sorted(v);q=lambda x:v[min(len(v)-1,int((len(v)-1)*x))]
    return {'packets':len(v),'p50_ms':q(.5),'p95_ms':q(.95),'p99_ms':q(.99),'max_ms':max(v),'mean_ms':statistics.mean(v)}
result={'platform':platform.platform(),'repeat':a.repeat,'batch_sha256':hashlib.sha256(a.batch.read_bytes()).hexdigest(),'incremental_sha256':hashlib.sha256(a.incremental.read_bytes()).hexdigest(),'all_raw_packets_timestamps_order_exact':True,'all_reference_core_digests_exact':True,'core_digests':{m:digest(v) for m,v in events.items()},'families':families,'paced':{'windows':len(chosen),'decoder_availability':{m:stats(lat[m]) for m in modes},'cpu_s':dict(paced_cpu),'outputs_at_terminal_flush':dict(finishes),'scope':'Paced saved-RF decoder publication only. Current production coordinator still has whole-window admission; this is NOT measured feeder end-to-end latency.'},'per_case':details,'working_pipeline_changed':False,'parent_reference':'same frozen historical RF and complete masks; no new labels, inference tuning or prospective claim','peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024 if platform.system()=='Darwin' else 1)}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'families':families,'paced':result['paced']},indent=2))

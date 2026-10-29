"""Bounded process workers. No SDR, feeder connections, or persistent IQ writes."""
import concurrent.futures as futures
import json,multiprocessing as mp,os,time
from collections import Counter,deque
from pathlib import Path

def cpu_list(value):
    result=set()
    for part in value.strip().split(','):
        if not part:continue
        ends=part.split('-')
        if len(ends)>2:raise ValueError('Invalid CPU range')
        a=int(ends[0]);b=int(ends[-1])
        if a<0 or b<a:raise ValueError('Invalid CPU range')
        result.update(range(a,b+1))
    return sorted(result)

def topology(sysroot=Path('/sys/devices/system/cpu'),allowed=None):
    """Use original CPU capacity, not current clock/load, and collapse SMT.

    On homogeneous ARM without capacity sysfs, identical MIDRs establish that
    there is no big/LITTLE split. Unknown heterogeneous machines require an
    explicit CPU list rather than guessing a performance class from GHz.
    """
    allowed=sorted(allowed if allowed is not None else (os.sched_getaffinity(0) if hasattr(os,'sched_getaffinity') else range(os.cpu_count() or 1)))
    def read(cpu,name):
        try:return (sysroot/f'cpu{cpu}'/name).read_text().strip()
        except OSError:return None
    groups={}
    for cpu in allowed:
        siblings=read(cpu,'topology/thread_siblings_list')
        key=tuple(cpu_list(siblings)) if siblings else (cpu,)
        groups.setdefault(key,[]).append(cpu)
    capacities={cpu:read(cpu,'cpu_capacity') for cpu in allowed}
    midrs={read(cpu,'regs/identification/midr_el1') for cpu in allowed}
    if all(capacities.values()):
        capacities={cpu:int(v) for cpu,v in capacities.items()};maximum=max(capacities.values())
        eligible={cpu for cpu,value in capacities.items() if value==maximum};source='linux_original_cpu_capacity';verified=True
    elif None not in midrs and len(midrs)==1:
        eligible=set(allowed);source='identical_arm_midr_homogeneous';verified=True
    else:
        eligible=set();source='performance_class_unknown';verified=False
    primary=[min(set(group)&eligible) for group in groups.values() if set(group)&eligible]
    return dict(logical_cpus=allowed,physical_core_count=len(groups),performance_cpus=sorted(primary),performance_core_count=len(primary),classification_verified=verified,detection=source)

def plan(config=None,info=None):
    supplied=json.loads(config.read_text()) if config and config.exists() else {}
    defaults=dict(workers='auto',reserve_cores=2,max_workers=2,cpus='auto',coherent_cpus='shared',coherent_threshold=.3,coherent_budget=24,optimized_dsp=False,sequence_acquisition=False,sequence_enabled=True,acquisition_enabled=True,optimized_v3=False,optimized_extended=False,coherent_pair_retry=False,shared_transport='files',cached_fir=False)
    if not isinstance(supplied,dict) or set(supplied)-set(defaults):raise ValueError('Unknown worker config option')
    cfg={**defaults,**supplied}
    if type(cfg['coherent_budget']) is not int or not 1<=cfg['coherent_budget']<=256:raise ValueError('Invalid coherent_budget')
    if isinstance(cfg['coherent_threshold'],bool) or not isinstance(cfg['coherent_threshold'],(int,float)) or not 0<cfg['coherent_threshold']<=1:raise ValueError('Invalid coherent_threshold')
    if type(cfg['optimized_dsp']) is not bool:raise ValueError('Invalid optimized_dsp')
    if type(cfg['acquisition_enabled']) is not bool:raise ValueError('Invalid acquisition_enabled')
    if type(cfg['sequence_enabled']) is not bool:raise ValueError('Invalid sequence_enabled')
    if type(cfg['sequence_acquisition']) is not bool:raise ValueError('Invalid sequence_acquisition')
    if cfg['sequence_acquisition'] and (not cfg['optimized_dsp'] or cfg['coherent_cpus']=='shared'):raise ValueError('Sequence/acquisition requires optimized split coherent workers')
    if type(cfg['optimized_v3']) is not bool:raise ValueError('Invalid optimized_v3')
    if cfg['optimized_v3'] and not cfg['sequence_acquisition']:raise ValueError('V3 requires the complete sequence/acquisition bundle')
    if type(cfg['optimized_extended']) is not bool:raise ValueError('Invalid optimized_extended')
    if cfg['optimized_extended'] and not cfg['optimized_v3']:raise ValueError('Optimized extended selection requires V3')
    if type(cfg['coherent_pair_retry']) is not bool:raise ValueError('Invalid coherent_pair_retry')
    if cfg['coherent_pair_retry'] and not cfg['optimized_v3']:raise ValueError('Coherent pair retry requires V3')
    if type(cfg['cached_fir']) is not bool:raise ValueError('Invalid cached_fir')
    if cfg['shared_transport'] not in ('files','ring'):raise ValueError('Invalid shared_transport')
    if cfg['shared_transport']=='ring' and not(cfg['optimized_v3'] and cfg['sequence_acquisition']):raise ValueError('Ring requires native v3 sequence/acquisition bundle')
    for key in ('reserve_cores','max_workers'):
        if type(cfg[key]) is not int or cfg[key]<(1 if key=='max_workers' else 0):raise ValueError('Invalid '+key)
    if cfg['workers']!='auto' and (type(cfg['workers']) is not int or cfg['workers']<1):raise ValueError('workers must be auto or a positive integer')
    info=topology() if info is None else info
    if cfg['cpus']=='auto':
        if not info['classification_verified']:raise ValueError('Performance class unavailable; explicitly configure cpus after inspecting hardware')
        candidates=info['performance_cpus'];reserve=min(cfg['reserve_cores'],max(0,len(candidates)-1));usable=candidates[reserve:]
    else:
        if not isinstance(cfg['cpus'],str):raise ValueError('cpus must be auto or a CPU range string')
        usable=cpu_list(cfg['cpus']);reserve=None
        if not usable or not set(usable)<=set(info['logical_cpus']):raise ValueError('Requested CPUs are outside the allowed affinity')
        # Manual overrides are visible and never silently called verified P cores.
    count=min(len(usable),cfg['max_workers']) if cfg['workers']=='auto' else cfg['workers']
    if count>len(usable) or count>cfg['max_workers']:raise ValueError('Worker count exceeds selected CPUs or configured cap')
    selected=usable[-count:]
    coherent=[]
    if cfg['coherent_cpus']!='shared':
        if not isinstance(cfg['coherent_cpus'],str):raise ValueError('coherent_cpus must be shared or a CPU range string')
        coherent=cpu_list(cfg['coherent_cpus'])
        if not coherent or not set(coherent)<=set(info['logical_cpus']):raise ValueError('Invalid coherent CPU selection')
        if set(coherent)&set(selected):raise ValueError('Coherent and DSP worker CPUs must be disjoint')
    return dict(**info,config=cfg,workers=count,worker_cpus=selected,coherent_cpus=coherent,reserved_performance_cpus=[c for c in info['performance_cpus'] if c not in selected],affinity_supported=hasattr(os,'sched_setaffinity'))

_DECODER=None
_RUNTIME=None
_ROLE="dsp"

def initialize(model,methods,runtime,cpu_assignments,companion=None,role="dsp",coherent_settings=None):
    global _DECODER,_RUNTIME,_ROLE
    _ROLE=role
    # Spawn avoids forking the live input threads or inherited receiver sockets.
    cpu=cpu_assignments.get(timeout=30)
    if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{cpu})
    os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
    from .runtime import RescueDecoder
    options=dict(coherent=methods.get('coherent',False),frontend='native',broad_crc=methods['crc'],neural=methods['neural'],methods=[k for k in ('timing','soft','matched','header','sic') if methods[k]])
    tuning=coherent_settings or dict(threshold=.3,budget=24)
    if role=='dsp' and methods.get('pulse') and (not tuning.get('optimized_dsp') or not tuning.get('optimized_v3')):
        raise ValueError('Native pulse filter requires optimized V3 DSP workers')
    options.update(coherent_threshold=tuning['threshold'],coherent_budget=tuning['budget'])
    if role=="coherent":_DECODER=CoherentWorker(tuning['threshold'],tuning['budget'],tuning.get('optimized_dsp',False),tuning.get('share_frontend',False),tuning.get('sequence_model'),tuning.get('optimized_v3',False),tuning.get('optimized_extended',False),tuning.get('coherent_pair_retry',False))
    elif companion:
        from .model_pair import paired_decoder
        _DECODER=paired_decoder(model,companion,**options)
    elif methods['neural']:
        from .model_cascade import cascade_decoder,production_paths
        paths=production_paths(Path(model).parent.parent)
        _DECODER=cascade_decoder(paths,**options)
    else:_DECODER=RescueDecoder(model,**options)
    if role=='coherent' and tuning.get('sequence_model'):
        _DECODER.decoder.coherent_enabled=tuning.get('coherent_enabled',True)
        _DECODER.decoder.sequence_enabled=tuning.get('sequence_enabled',True)
        _DECODER.decoder.acquisition_enabled=tuning.get('acquisition_enabled',True)
    if role!='coherent' and tuning.get('optimized_dsp',False):
        from .pipeline_native import enable_decoder
        enable_decoder(_DECODER,'producer' if tuning.get('share_frontend') else None)
        if tuning.get('optimized_v3',False):
            from .pipeline_v3 import enable_v3
            enable_v3(_DECODER,'producer' if tuning.get('share_frontend') else None)
    if role=='dsp' and methods.get('pulse'):
        from .pulse_live import production_model
        _DECODER.pulse_model=production_model(Path(model).parent/'pulse-discriminant.json')
    _RUNTIME=Path(runtime);_RUNTIME.mkdir(parents=True,exist_ok=True)


class CoherentWorker:
    """Independent coherent branch; consumes the same immutable tmpfs UC8 job."""
    def __init__(self,threshold=.3,budget=24,optimized_dsp=False,share_frontend=False,sequence_model=None,optimized_v3=False,optimized_extended=False,coherent_pair_retry=False):
        from .coherent_fast import FastCoherentDecoder
        self.decoder=FastCoherentDecoder(source='coherent',threshold=threshold,budget=budget)
        self.backend=None
        if optimized_dsp:
            from .pipeline_native import FastBackend
            if optimized_v3:
                if optimized_extended:
                    from .coherent_extended_opt import ExtendedNeonBackend as Backend
                else:
                    from .pipeline_v3 import BackendV3 as Backend
                self.backend=Backend('consumer' if share_frontend else None)
            else:self.backend=FastBackend('consumer' if share_frontend else None)
            self.decoder.score_function=self.backend.coherent_scores
        if sequence_model:
            if self.backend is None:raise ValueError('Sequence/acquisition requires the native backend')
            import numpy as np
            from .sequence_live import SequenceAcquisitionDecoder
            h=json.loads(Path(sequence_model).read_text());engine=SequenceAcquisitionDecoder
            if optimized_v3:
                from .pipeline_v3 import SequenceV3
                engine=SequenceV3
            self.decoder=engine(np.array(h['h_real'])+1j*np.array(h['h_imag']),self.backend,threshold,budget)
            self.decoder.pair_retry=coherent_pair_retry
    def decode(self,path,stock=(),block_range=None,raw_events=False,source_first=0,total_samples=None):
        from .native import iq_blocks
        blocks=(self.backend.iq_blocks if self.backend else iq_blocks)(path,.05,block_range=block_range,source_first=source_first,total_samples=total_samples)
        rows,detail=self.decoder.decode(path,blocks=blocks,raw_events=True)
        events=[dict(preamble_score=0.,crc=0,provisional=True,**r) for r in rows['coherent']]
        work={'coherent_cpu_s':detail['cpu_s'],'coherent_wall_s':detail['wall_s']}
        for name,value in detail.get('branch_cpu_s',{}).items():
            if name.startswith('method_'):work['cpu_'+name]=value
        for key,value in detail['counts'].items():work[key if key.startswith('coherent_') else 'coherent_'+key]=value
        return (events if raw_events else merge_events([events])),work

def block_ranges(byte_count,workers):
    if byte_count<=0 or byte_count%2:raise ValueError('Empty or truncated UC8 data')
    # Same 50 ms / 120,000 raw-sample boundaries as the serial decoder.
    blocks=(byte_count//2+119999)//120000
    count=min(workers,blocks)
    return [(i*blocks//count,(i+1)*blocks//count) for i in range(count)]

def merge_events(parts):
    """Replay emission order, then apply the serial cross-block dedupe once.

    Dedupe is not transitive. Deduping independently before merging can lose a
    third frame when an earlier frame suppresses the middle frame at a seam.
    Broad CRC remains intentionally raw and quarantined.
    """
    from .dsp import SAMPLES
    events=[];seen={}
    rows=[row for group in parts for row in group]
    # Preserve every existing decoder's attribution before admitting coherent
    # additions, including duplicates on adjacent worker/block boundaries.
    priority={'coherent':1,'sequence':2,'acquisition':3,'pulse':4}
    rows.sort(key=lambda r:priority.get(r['source'],0))
    for row in rows:
        if row['source']!='broad_crc':
            key=row['message_hex'];sample=row['sample_4msps']
            previous=seen.setdefault(key,[])
            if any(abs(sample-other)<SAMPLES for other in previous):continue
            previous.append(sample)
        events.append(row)
    events.sort(key=lambda r:(r['sample_4msps'],r['source']))
    return events

def decode_job(path,block_range,stock=(),source_first=0,total_samples=None,policy=None):
    begin=time.monotonic();cpu=time.process_time()
    from deadsb.policy import reduced
    with reduced(_DECODER,_ROLE,policy) as skip:
        if skip:
            events=[];work=dict(neural_windows=0,budget_dropped=0,late_blocks=0,max_block_s=0.,budget_skipped_jobs=1)
        else:
            events,work=_DECODER.decode(path,stock=stock,block_range=block_range,raw_events=True,source_first=source_first,total_samples=total_samples)
    work['budget_level_'+str(policy.get('level',0) if policy else 0)]=1
    work.update(worker_role=_ROLE,worker_pid=os.getpid(),worker_cpus=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else [],worker_cpu_s=time.process_time()-cpu,job_wall_s=time.monotonic()-begin,chunk_started_s=begin,chunk_finished_s=time.monotonic(),block_range=block_range)
    return events,work

class WorkerPool:
    def __init__(self,model,methods,runtime,selection,companion=None):
        self.selection=selection;self.pending=deque();self.completed=Counter();self.cpu_seconds=Counter();self.affinities={};self.roles={};self.jobs=0;self.recent_overlap=deque(maxlen=120)
        self.runtime=Path(runtime);self.runtime.mkdir(parents=True,exist_ok=True);self.job_paths=set()
        context=mp.get_context('spawn');self.cpu_assignments=context.Queue(selection['workers'])
        for index in range(selection['workers']):self.cpu_assignments.put(selection['worker_cpus'][index] if selection['worker_cpus'] else None)
        self.coherent_executor=None;self.coherent_assignments=None
        separate=selection.get('coherent_cpus',[]) if methods.get('coherent') or selection.get('config',{}).get('sequence_acquisition') else []
        dsp_methods={**methods,'coherent':False} if separate else methods
        tuning={k:selection.get('config',{}).get('coherent_'+k,v) for k,v in dict(threshold=.3,budget=24).items()}
        tuning['coherent_enabled']=methods.get('coherent',False)
        tuning['acquisition_enabled']=selection.get('config',{}).get('acquisition_enabled',True)
        tuning['sequence_enabled']=selection.get('config',{}).get('sequence_enabled',True)
        tuning.update(optimized_dsp=selection.get('config',{}).get('optimized_dsp',False),share_frontend=bool(separate),optimized_v3=selection.get('config',{}).get('optimized_v3',False),optimized_extended=selection.get('config',{}).get('optimized_extended',False),coherent_pair_retry=selection.get('config',{}).get('coherent_pair_retry',False))
        if selection.get('config',{}).get('sequence_acquisition',False):
            if not separate or not tuning['optimized_dsp']:raise ValueError('Sequence/acquisition requires split optimized coherent workers')
            tuning['sequence_model']=str(Path(model).parent/'pulse-sequence.json')
        self.executor=futures.ProcessPoolExecutor(max_workers=selection['workers'],mp_context=context,initializer=initialize,initargs=(str(model),dsp_methods,str(runtime),self.cpu_assignments,str(companion) if companion else None,'dsp',tuning))
        if separate:
            self.coherent_assignments=context.Queue(len(separate))
            for cpu in separate:self.coherent_assignments.put(cpu)
            self.coherent_executor=futures.ProcessPoolExecutor(max_workers=len(separate),mp_context=context,initializer=initialize,initargs=(str(model),dsp_methods,str(runtime),self.coherent_assignments,None,'coherent',tuning))
    def submit_ranges(self,path,ranges,stock=(),source_first=0,total_samples=None):
        tasks=[self.executor.submit(decode_job,str(path),bounds,stock,source_first,total_samples,getattr(self,'job_policy',None)) for bounds in ranges]
        if getattr(self,'coherent_executor',None):
            tasks += [self.coherent_executor.submit(decode_job,str(path),bounds,(),source_first,total_samples,getattr(self,'job_policy',None)) for bounds in ranges]
        return tasks
    def submit(self,item,stock=()):
        if len(self.pending)>=self.selection['workers']:raise RuntimeError('Bounded worker pool full')
        ranges=block_ranges(len(item[3]),self.selection['workers'])
        # One shared immutable tmpfs file, not a copied RF second per subprocess.
        path=self.runtime/f'job-{os.getpid()}-{self.jobs}.uc8'
        path.write_bytes(item[3]);self.job_paths.add(path)
        submitted=time.monotonic()
        tasks=self.submit_ranges(path,ranges,stock)
        self.pending.append((item,tasks,submitted,path));self.jobs+=1
    def ready(self):
        return bool(self.pending and all(task.done() for task in self.pending[0][1]))
    def pop(self,raw_events=False):
        # Deliver RF seconds and their chunks in original block/emission order.
        if not self.ready():return None
        item,tasks,submitted,path=self.pending.popleft()
        try:parts=[task.result() for task in tasks]
        finally:self.clean_job(path)
        events=([row for rows,detail in parts for row in rows] if raw_events else merge_events([rows for rows,detail in parts]));work={};chunks=[]
        for rows,detail in parts:
            pid=str(detail['worker_pid']);self.affinities[pid]=detail.get('worker_cpus',[]);self.completed[pid]+=1;self.cpu_seconds[pid]+=detail['worker_cpu_s']
            if hasattr(self,'roles'):self.roles[pid]=detail.get('worker_role','dsp')
            chunks.append({**{key:detail[key] for key in ('worker_pid','worker_cpus','worker_cpu_s','chunk_started_s','chunk_finished_s','block_range')},'worker_role':detail.get('worker_role','dsp')})
            for key,value in detail.items():
                if key in ('worker_role','worker_pid','worker_cpus','chunk_started_s','chunk_finished_s','block_range','job_wall_s'):continue
                work[key]=max(work.get(key,0),value) if key=='max_block_s' else work.get(key,0)+value
        latency=time.monotonic()-submitted
        # Positive overlap proves simultaneous execution, unlike balanced counts.
        overlap=max(0.,min(c['chunk_finished_s'] for c in chunks)-max(c['chunk_started_s'] for c in chunks)) if len(chunks)>1 else 0.
        self.recent_overlap.append(overlap)
        work.update(execution_span_s=max(c['chunk_finished_s'] for c in chunks)-min(c['chunk_started_s'] for c in chunks),outputs=len(events),result_latency_s=latency,job_wall_s=latency,worker_pid=chunks[0]['worker_pid'],worker_pids=sorted({c['worker_pid'] for c in chunks}),chunks=chunks,parallel_overlap_s=overlap)
        return item,events,work
    def report(self):
        return {**self.selection,'pending_jobs':len(self.pending),'submitted_jobs':self.jobs,'affinity_by_pid':dict(self.affinities),'role_by_pid':dict(getattr(self,'roles',{})),'completed_by_pid':dict(self.completed),'cpu_seconds_by_pid':dict(self.cpu_seconds),'max_pending_jobs':self.selection['workers'],'max_pending_chunks':self.selection['workers']**2,'mean_parallel_overlap_s':sum(self.recent_overlap)/len(self.recent_overlap) if self.recent_overlap else 0.,'chunking':'contiguous_50ms_blocks_per_rf_second','delivery':'sample_order','optimized_v3':self.selection.get('config',{}).get('optimized_v3',False),'optimized_extended':self.selection.get('config',{}).get('optimized_extended',False),'coherent_pair_retry':self.selection.get('config',{}).get('coherent_pair_retry',False),'sequence_enabled':self.selection.get('config',{}).get('sequence_enabled',True) and self.selection.get('config',{}).get('sequence_acquisition',False),'acquisition_enabled':self.selection.get('config',{}).get('acquisition_enabled',True) and self.selection.get('config',{}).get('sequence_acquisition',False),'sequence_acquisition':self.selection.get('config',{}).get('sequence_acquisition',False),'optimized_dsp':self.selection.get('config',{}).get('optimized_dsp',False),'shared_frontend':bool(getattr(self,'coherent_executor',None) and self.selection.get('config',{}).get('optimized_dsp',False)),'forwarding_enabled':False}
    def clean_job(self,path):
        path.unlink(missing_ok=True);self.job_paths.discard(path)
        for cache in path.parent.glob(path.name+'.fast-*'):cache.unlink(missing_ok=True)
    def close(self):
        try:
            self.executor.shutdown(wait=True,cancel_futures=True)
            if getattr(self,'coherent_executor',None):self.coherent_executor.shutdown(wait=True,cancel_futures=True)
        finally:
            for path in list(self.job_paths):self.clean_job(path)
            self.job_paths.clear();self.cpu_assignments.close();self.cpu_assignments.join_thread()
            if getattr(self,"coherent_assignments",None):self.coherent_assignments.close();self.coherent_assignments.join_thread()

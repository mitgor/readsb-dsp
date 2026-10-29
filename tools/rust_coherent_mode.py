#!/usr/bin/env python3
"""Rust coherent deployment and persistent guarded rollback to C.

Run on the receiver as root. Only the rescue shadow service is restarted.
"""
import argparse,ctypes,hashlib,json,os,shutil,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path('/home/pi/adsb-neural-rescue');STATE=Path('/var/lib/adsb-coherent-rust/active.json')
PROTECTED=('readsb','fr24feed','adsb-rescue-feed','adsbexchange-feed','adsb-far-capture')
CONFIGS=('/etc/default/adsb-rescue-workers.json','/etc/default/adsb-rescue.json','/etc/default/readsb','/etc/fr24feed.ini')
FILES={'src/rescue/_coherent.so':'experiments/rust-live/.work/candidate/_coherent.so','src/rescue/_coherent_pair.so':'experiments/rust-live/.work/candidate/_coherent_pair.so','src/rescue/coherent_rust.rs':'src/rescue/coherent_rust.rs','src/rescue/coherent_peaks.c':'src/rescue/coherent_peaks.c'}
RUNTIME=Path('/run/adsb-coherent-rust/guard.json')

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pid(n):return int(subprocess.check_output(['systemctl','show',n,'-p','MainPID','--value'],text=True).strip())
def snapshot():
 s=read('/run/adsb-rescue/status.json');f=read('/run/adsb-rescue/feed-status.json');stats=read('/run/readsb/stats.json')
 with urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=5) as r:fr=json.load(r)
 crc=s.get('crc_verification',{}).get('archive',{})
 return {'unix':time.time(),'pids':{n:pid(n) for n in PROTECTED},'shadow_pid':pid('adsb-rescue-shadow'),'started_unix':s['started_unix'],'updated_unix':s['updated_unix'],'feed_updated_unix':f['updated_unix'],'threads_alive':s['threads_alive'],'gain_db':s['health']['gain_db'],'methods':s['method_switches'],'worker_config':s['workers']['config'],'worker_roles':s['workers']['role_by_pid'],'workers':s['workers']['affinity_by_pid'],'pending':s['workers']['pending_jobs'],'mean_latency_s':s['workers']['mean_batch_latency_s'],'aligned_seconds':s['counts'].get('aligned_seconds',0),'shed':s['workers']['incomplete_rf_seconds_shed'],'samples':{k:stats['total']['local'][k] for k in ('samples_lost','samples_dropped')},'feed':{'stock_connected':f['stock_connected'],'fr24_routed':f['fr24_routed'],'counts':{k:f['counts'].get(k,0) for k in ('stock_bytes_relayed','dsp_frames_relayed','relayed_coherent')},'upstream_error':f.get('upstream_error')},'fr24':{k:fr.get(k) for k in ('feed_status','rx_connected','feed_last_ac_sent_time','feed_num_ac_tracked')},'crc_archive':{'disk_bytes':sum(x['bytes'] for x in crc.get('files',[])),'ram_bytes':crc.get('compressed_ram_bytes',0),'error':crc.get('error'),'saved_files':len(crc.get('files',[]))},'config_sha256':{p:sha(p) for p in CONFIGS},'temperature_c':int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000}
def healthy(old,s):
 now=time.time()
 assert all(s['pids'].values()) and s['pids']==old['pids'],'Protected service PID changed'
 assert s['config_sha256']==old['config_sha256'],'Configuration changed'
 assert s['samples']==old['samples'],'Sample loss/drop counter changed'
 assert s['gain_db']==old['gain_db'] and s['methods']==old['methods'] and s['worker_config']==old['worker_config'],'Decoder selection changed'
 assert now-s['updated_unix']<15 and now-s['feed_updated_unix']<6,'Stale status'
 assert s['threads_alive'] and s['feed']['stock_connected'] and s['feed']['fr24_routed'],'Relay path unhealthy'
 assert s['fr24']['feed_status']=='connected' and str(s['fr24']['rx_connected'])=='1','FR24 disconnected'
 assert now-int(s['fr24']['feed_last_ac_sent_time'] or 0)<90,'FR24 uploads stale'
 assert s['mean_latency_s']<.75 and s['pending']<=4 and s['temperature_c']<75,'Worker health bound exceeded'
 assert not s['crc_archive']['error'],'Archive error'
def atomic(dest,data,record):
 temp=dest.with_name(dest.name+'.rust-new');temp.write_bytes(data);os.chmod(temp,record['mode']);os.chown(temp,record['uid'],record['gid']);os.replace(temp,dest)
def restore(backup):
 for dest,record in read(backup/'files.json').items():
  p=Path(dest)
  if record['existed']:atomic(p,(backup/record['backup']).read_bytes(),record)
  else:p.unlink(missing_ok=True)
 subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
def mapped(s):
 result={}
 for worker,role in s['worker_roles'].items():
  if role!='coherent':continue
  maps=Path('/proc')/worker/'maps';lines=maps.read_text().splitlines();found=[]
  for name in ('_coherent.so','_coherent_pair.so'):
   path=ROOT/'src/rescue'/name;ino=path.stat().st_ino
   assert any(len(parts:=line.split())>=6 and parts[4]==str(ino) and parts[-1]==str(path) for line in lines),f'{worker} does not map installed {name}'
   found.append(name)
  result[worker]=found
 assert len(result)==2,'Expected two coherent workers'
 return result

def save(path,data):
    temp=path.with_name(path.name+'.new');temp.write_text(json.dumps(data,indent=2)+'\n');os.replace(temp,path)

def backend_markers():
    result={}
    for name in ('_coherent.so','_coherent_pair.so'):
        lib=ctypes.CDLL(str(ROOT/'src/rescue'/name));lib.rescue_coherent_backend.restype=ctypes.c_char_p
        assert lib.rescue_coherent_init()==0
        result[name]=lib.rescue_coherent_backend().decode()
        assert result[name].startswith('rust-1.99.1/std-sort/')
    return result

def rollback(reason='manual'):
    if not STATE.exists():return {'state':'inactive'}
    state=read(STATE)
    if state['state'] not in ('active','activating','rollback_failed'):return
    backup=Path(state['backup'])
    try:
        restore(backup)
        for name,record in read(backup/'files.json').items():
            if record['existed']:assert sha(name)==record['sha256']
        state.update(state='rolled_back',reason=reason,rolled_back_unix=time.time());save(STATE,state)
        return state
    except BaseException as error:
        state.update(state='rollback_failed',error=repr(error));save(STATE,state);raise

def activate(stage,observe):
    if STATE.exists():assert read(STATE)['state']=='rolled_back','Rust release already active/incomplete'
    proof=read(stage/'pi.json');assert proof['windows']>=3000
    for mode,name in [('base','_coherent.so'),('pair','_coherent_pair.so')]:
        b=proof['branches'][mode]
        assert b['parity']['packet_rows_flags_repairs_exact'] and b['parity']['hard_bits_exact']
        assert b['exact_all_arrays'] and b['cpu_saving_percent']>0,'Release parity/performance gate failed'
        assert proof['controls'][mode]['augmented_windows']>=8192 and proof['controls'][mode]['peak_selector_cases']>=500
        assert sha(ROOT/'src/rescue'/name)==b['reference_sha256'],'Baseline changed after validation'
        assert sha(stage/'experiments/rust-live/.work/candidate'/name)==b['candidate_sha256'],'Candidate changed after validation'
    before=snapshot();healthy(before,before)
    assert before['crc_archive']['disk_bytes']+before['crc_archive']['ram_bytes']+8*1024**2<512*1024**2,'Archive lacks shutdown-save room'
    backup=Path('/var/backups')/('adsb-coherent-rust-'+str(time.time_ns()));backup.mkdir(mode=0o700);records={};hashes={}
    for index,(dest,source) in enumerate(FILES.items()):
        p=ROOT/dest;stat=p.stat() if p.exists() else p.parent.stat();record={'existed':p.exists(),'backup':f'file-{index}','mode':stat.st_mode&0o777 if p.exists() else 0o644,'uid':stat.st_uid,'gid':stat.st_gid}
        if p.exists():shutil.copy2(p,backup/record['backup']);record['sha256']=sha(p)
        records[str(p)]=record;hashes[dest]=sha(stage/source)
    save(backup/'files.json',records)
    report={'before':before,'backup':str(backup),'installed_sha256':hashes,'proof_sha256':sha(stage/'pi.json'),'samples':[],'activated':False}
    save(backup/'deployment.json',report);save(STATE,{'state':'activating','backup':str(backup),'installed_sha256':hashes})
    try:
        for dest,source in FILES.items():atomic(ROOT/dest,(stage/source).read_bytes(),records[str(ROOT/dest)]);assert sha(ROOT/dest)==hashes[dest]
        report['backend_markers']=backend_markers();switched=time.time()
        subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
        for _ in range(45):
            s=snapshot()
            if s['started_unix']>switched and s['aligned_seconds']>=5:break
            time.sleep(2)
        else:raise RuntimeError('Rust workers did not become ready')
        since=time.time();first=s
        while True:
            healthy(before,s);report['samples'].append(s);report['mapped_libraries']=mapped(s);save(backup/'deployment.json',report)
            if time.time()-since>=observe:break
            time.sleep(10);s=snapshot()
        assert s['aligned_seconds']-first['aligned_seconds']>=observe*.8,'Aligned RF throughput fell'
        assert s['shed']-first['shed']<=max(5,observe*.05),'RF shedding exceeded bound'
        for key in ('stock_bytes_relayed','dsp_frames_relayed','relayed_coherent'):assert s['feed']['counts'][key]>first['feed']['counts'][key],key+' stalled'
        for dest in FILES:assert sha(ROOT/dest)==hashes[dest]
        report['activated']=True;save(backup/'deployment.json',report)
        save(STATE,{'state':'active','backup':str(backup),'installed_sha256':hashes,'activated_unix':time.time(),'baseline_samples':s['samples'],'source_health':{'gain_db':s['gain_db'],'methods':s['methods']}})
        print(json.dumps({'activated':True,'backup':str(backup),'aligned_seconds':s['aligned_seconds']-first['aligned_seconds'],'coherent_frames_relayed':s['feed']['counts']['relayed_coherent']-first['feed']['counts']['relayed_coherent'],'protected_pids_unchanged':True},indent=2))
    except BaseException as error:
        report['error']=repr(error);rollback('activation: '+repr(error));report['rolled_back']=True;save(backup/'deployment.json',report);raise

def watch_check(s,previous,*,now=None):
    now=time.time() if now is None else now
    assert now-s['updated_unix']<20 and now-s['feed_updated_unix']<10,'Stale DSP or relay status'
    assert s['threads_alive'] and s['feed']['stock_connected'] and s['feed']['fr24_routed'],'Receiver/relay path unhealthy'
    assert s['fr24']['feed_status']=='connected' and str(s['fr24']['rx_connected'])=='1','FR24 disconnected'
    assert now-int(s['fr24']['feed_last_ac_sent_time'] or 0)<90,'FR24 uploads stale'
    assert s['pending']<=4 and s['mean_latency_s']<.75,'Worker backlog/latency bound exceeded'
    assert s['temperature_c']<80,'Temperature exceeded bound'
    assert all(s['pids'].values()),'A protected service stopped'
    if previous and previous['started_unix']==s['started_unix']:
        assert s['samples']==previous['samples'],'Sample-loss/drop count increased'
        assert s['aligned_seconds']>previous['aligned_seconds'],'DSP RF processing stalled'
        assert s['feed']['counts']['stock_bytes_relayed']>previous['feed']['counts']['stock_bytes_relayed'],'Stock relay stalled'

def watch(interval,failures):
    count=0;previous=None;first=True;starts=[];last_start=None
    while STATE.exists() and read(STATE)['state']=='active':
        if first:time.sleep(interval);first=False
        state=read(STATE)
        try:
            s=snapshot()
            if s['started_unix']!=last_start:
                starts=[t for t in starts if time.time()-t<180];starts.append(time.time());last_start=s['started_unix']
            assert len(starts)<3,'Repeated DSP service restarts'
            # Give normal boot/worker startup time to establish alignment.
            if time.time()-s['started_unix']<30:previous=None;time.sleep(interval);continue
            watch_check(s,previous)
            if s['methods'].get('coherent',True):mapped(s)
            for dest,expected in state['installed_sha256'].items():assert sha(ROOT/dest)==expected,'Installed Rust file changed: '+dest
            previous=s;count=0;save(RUNTIME,{'state':'healthy','updated_unix':time.time(),'failures':0,'aligned_seconds':s['aligned_seconds']})
        except Exception as error:
            count+=1;save(RUNTIME,{'state':'degraded','updated_unix':time.time(),'failures':count,'error':repr(error)})
            if count>=failures:
                rollback('watchdog: '+repr(error));save(RUNTIME,{'state':'rolled_back','updated_unix':time.time(),'reason':repr(error)});return
        time.sleep(interval)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('activate','rollback','status','watch'));p.add_argument('--stage',type=Path);p.add_argument('--observe',type=int,default=120);p.add_argument('--interval',type=int,default=15);p.add_argument('--failures',type=int,default=3);a=p.parse_args()
    if a.action=='status':print(json.dumps({'release':read(STATE) if STATE.exists() else {'state':'inactive'},'guard':read(RUNTIME) if RUNTIME.exists() else None},indent=2));return
    assert os.geteuid()==0,'Run as root'
    STATE.parent.mkdir(mode=0o700,parents=True,exist_ok=True);RUNTIME.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    assert STATE.parent.stat().st_uid==0 and not STATE.parent.is_symlink(),'Unsafe release state directory'
    if a.action=='activate':assert a.stage and a.observe>=60;activate(a.stage,a.observe)
    elif a.action=='rollback':print(json.dumps(rollback(),indent=2))
    else:assert a.interval>=10 and a.failures>=2;watch(a.interval,a.failures)
if __name__=='__main__':main()

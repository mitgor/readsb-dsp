"""45s read-only test listener+recorder; no DSP producer or feeder attachment."""
import asyncio,hashlib,json,resource,runpy,time,os
from pathlib import Path
from types import SimpleNamespace
from async_relay import serve,SOURCES
D=Path(os.environ.get('ADSB_ASYNC_PROBE_DIR','/dev/shm/adsb-async-relay-20261030/data'))
old=runpy.run_path('/var/lib/adsb-fr24-stock-trial-20261030/trial.py')
def health():
 s=old['snapshot']();baseline=json.loads(Path('/run/adsb-fr24-stock-trial-20261030/extended-status.json').read_text())['baseline'];old['health'](baseline,s,True)
 return {k:s[k] for k in ['pids','fr24_pid','configs','gain_db','methods']}
async def capture(name,port):
 r,w=await asyncio.open_connection('127.0.0.1',port);end=time.monotonic()+45;offset=0
 try:
  with (D/(name+'.beast')).open('wb') as out,(D/(name+'.chunks.jsonl')).open('w') as idx:
   while time.monotonic()<end:
    try:raw=await asyncio.wait_for(r.read(65536),1)
    except TimeoutError:continue
    if not raw:raise RuntimeError('Test input closed')
    assert offset+len(raw)<16*1024**2
    out.write(raw);idx.write(json.dumps(dict(at=time.monotonic(),offset=offset,bytes=len(raw)))+'\n');offset+=len(raw)
 finally:w.close();await w.wait_closed()
async def watch(before):
 for _ in range(9):await asyncio.sleep(5);assert health()==before
async def main():
 D.mkdir(exist_ok=False);before=health();switch=D/'switches.json';switch.write_text(json.dumps(before['methods']));switch.write_text(json.dumps({s:before['methods'].get(s,False) for s in SOURCES}))
 cpu=time.process_time();start=time.monotonic();task=asyncio.create_task(serve(SimpleNamespace(runtime=D/'runtime',switches=switch,stock_port=30005,port=0,seconds=50)))
 for _ in range(100):
  if (D/'runtime/endpoint.json').exists():break
  await asyncio.sleep(.01)
 endpoint=json.loads((D/'runtime/endpoint.json').read_text());await asyncio.gather(capture('stock',30005),capture('asynchronous',endpoint['port']),watch(before));await task;after=health();assert before==after
 (D/'probe.json').write_text(json.dumps(dict(before=before,after=after,cpu_s=time.process_time()-cpu,wall_s=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in D.glob('*') if p.is_file()},scope='Process includes dual TCP recording, relay, RAM status and periodic health checks; no DSP inference/producer/FR24 connection. Peak RSS includes imports.'),indent=2))
asyncio.run(main())

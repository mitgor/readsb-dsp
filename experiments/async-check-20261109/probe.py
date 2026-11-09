"""Finite read-only stock/production/async fan-out comparison; no DSP producer."""
import asyncio,json,time,hashlib,resource,subprocess,urllib.request,os
from pathlib import Path
from types import SimpleNamespace
from async_relay import serve,SOURCES
D=Path(os.environ['PROBE_DIR'])
def health():
 s=json.loads(Path('/run/adsb-rescue/status.json').read_text());m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=3));assert m['feed_status']=='connected' and str(m['rx_connected'])=='1';local=s['health']['local']
 return dict(pids={u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in ['readsb','fr24feed','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture']},configs={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['/etc/default/adsb-rescue.json','/etc/default/adsb-rescue-workers.json']},gain=s['health']['gain_db'],methods=s['method_switches'],sample_loss={k:local.get(k,0) for k in ['samples_lost','samples_dropped']})
async def capture(name,port):
 reader,writer=await asyncio.open_connection('127.0.0.1',port);end=time.monotonic()+45;offset=0
 try:
  with (D/(name+'.beast')).open('wb') as out,(D/(name+'.chunks.jsonl')).open('w') as idx:
   while time.monotonic()<end:
    try:b=await asyncio.wait_for(reader.read(65536),1)
    except TimeoutError:continue
    if not b:raise RuntimeError('Input disconnected')
    assert offset+len(b)<16*1024**2
    out.write(b);idx.write(json.dumps(dict(at=time.monotonic(),offset=offset,bytes=len(b)))+'\n');offset+=len(b)
 finally:writer.close();await writer.wait_closed()
async def watch(before):
 for _ in range(9):await asyncio.sleep(5);assert health()==before,'Protected health changed; owned probe aborts'
async def main():
 D.mkdir(exist_ok=False);before=health();switch=D/'switches.json';switch.write_text(json.dumps({k:before['methods'].get(k,False) for k in SOURCES}));cpu=time.process_time();start=time.monotonic()
 task=asyncio.create_task(serve(SimpleNamespace(runtime=D/'runtime',switches=switch,stock_port=30005,port=0,seconds=50)))
 try:
  for _ in range(100):
   if (D/'runtime/endpoint.json').exists():break
   await asyncio.sleep(.01)
  port=json.loads((D/'runtime/endpoint.json').read_text())['port']
  await asyncio.gather(capture('stock',30005),capture('asynchronous',port),capture('production',31005),watch(before));await task;after=health();assert before==after
  meta=dict(before=before,after=after,cpu_s=time.process_time()-cpu,wall_s=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in D.glob('*') if p.is_file()},scope='Includes relay, three TCP recordings, RAM status, imports and health polling; stock only on isolated asynchronous output, no real DSP producer or FR24 client.')
  (D/'probe.json').write_text(json.dumps(meta,indent=2)+'\n')
 finally:
  if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
asyncio.run(main())

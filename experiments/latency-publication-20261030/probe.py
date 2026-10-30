"""Finite read-only localhost probe. Never opens SDR/mirror or feeder input."""
import asyncio,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path('/dev/shm/adsb-latency-20261030');UNITS=('readsb','fr24feed','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture','adsbexchange-feed')
def health():
 r=json.loads(Path('/run/readsb/stats.json').read_text());s=json.loads(Path('/run/adsb-rescue/status.json').read_text());c=json.loads(Path('/run/adsb-far-capture/status.json').read_text());t=json.loads(Path('/run/adsb-fr24-stock-trial-20261030/status.json').read_text())
 return dict(pids={n:subprocess.check_output(['systemctl','show',n,'-p','MainPID','--value'],text=True).strip() for n in UNITS},samples={k:r['total']['local'][k] for k in ('samples_lost','samples_dropped')},methods=s['method_switches'],gain=r['gain_db'],cap=c['disk_limit_bytes'],trial_state=t['state'],configs={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['/etc/default/readsb','/etc/default/adsb-rescue.json','/etc/default/adsb-rescue-workers.json','/etc/default/adsb-far-capture.json','/etc/fr24feed.ini']},source={str(p.relative_to('/home/pi/adsb-neural-rescue')):hashlib.sha256(p.read_bytes()).hexdigest() for d in ['src/rescue','models'] for p in (Path('/home/pi/adsb-neural-rescue')/d).rglob('*') if p.is_file() and p.suffix in ('.py','.so','.onnx')})
async def capture(name,port):
 reader,writer=await asyncio.open_connection('127.0.0.1',port);end=time.monotonic()+45;offset=0
 try:
  with (ROOT/(name+'.beast')).open('wb') as raw,(ROOT/(name+'.chunks.jsonl')).open('w') as idx:
   while time.monotonic()<end:
    try:b=await asyncio.wait_for(reader.read(65536),1)
    except asyncio.TimeoutError:continue
    if not b:raise RuntimeError('source_closed')
    assert offset+len(b)<16*1024**2
    raw.write(b);idx.write(json.dumps(dict(at=time.monotonic(),unix=time.time(),offset=offset,bytes=len(b)))+'\n');offset+=len(b)
 finally:writer.close();await writer.wait_closed()
async def monitor(before):
 for _ in range(9):
  await asyncio.sleep(5);after=health();assert after==before,'Protected health/configuration changed'
async def main():
 ROOT.mkdir(exist_ok=False);before=health();await asyncio.gather(capture('stock',30005),capture('combined',31005),monitor(before));after=health();assert before==after
 cadence=[]
 for line in subprocess.check_output(['sudo','-n','journalctl','-u','fr24feed','--since','2026-10-30 06:57:45 UTC','--no-pager','-o','json'],text=True).splitlines():
  r=json.loads(line);m=r.get('MESSAGE','')
  if '[feed][i]sent ' in m:cadence.append(int(r['__REALTIME_TIMESTAMP'])/1e6)
 (ROOT/'result.json').write_text(json.dumps(dict(before=before,after=after,send_times=cadence,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in ROOT.iterdir() if p.is_file()}),indent=2))
asyncio.run(main())

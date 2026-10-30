"""Finite idle-mirror capture, never consumes an active consumer's work."""
import collections,hashlib,json,os,runpy,signal,socket,sys,threading,time
from pathlib import Path
from rescue.neural_spool import Spool
from rescue.shadow import LiveInput,valid_df17,CORRECTION_TICKS
from rescue.wire import BeastParser
D=Path(sys.argv[1]);assert str(D).startswith('/dev/shm/');D.mkdir();stop=threading.Event()
old=runpy.run_path('/var/lib/adsb-fr24-stock-trial-20261030/trial.py')
def health():
 s=old['snapshot']();baseline=json.loads(Path('/run/adsb-fr24-stock-trial-20261030/extended-status.json').read_text())['baseline'];old['health'](baseline,s,True)
 return {k:s[k] for k in ('pids','fr24_pid','configs','gain_db','methods','stock','fr24','capture')}
before=health();spool=Spool('/run/adsb-rescue/neural');assert not spool.active(),'Existing consumer: do not interfere'
live=LiveInput(D/'unused.sock',(0.,0.),indexed_stock_history=True);live.start(include_iq=False)
stock={};relay=[];positions=[];cases=[];errors=[];owned=False
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
def receive():
 try:
  with socket.create_connection(('127.0.0.1',31005),timeout=2) as s:
   s.settimeout(.5);p=BeastParser()
   while not stop.is_set():
    try:data=s.recv(65536)
    except socket.timeout:continue
    if not data:raise RuntimeError('Relay disconnected')
    for r in p.feed(data):
     if valid_df17(r['message_hex']):relay.append(dict(r,ticks=r['ticks_12mhz']-CORRECTION_TICKS,arrival=time.time()))
 except Exception as e:errors.append(repr(e));stop.set()
t=threading.Thread(target=receive);t.start();start=time.monotonic();lastheart=0;lastpos=0;closed=None
try:
 while not stop.wait(.01):
  now=time.monotonic()
  frames,_=live.snapshot()
  for r in frames:stock[(r['ticks'],r['message_hex'])]=r
  if now-lastpos>=1:
   a=json.loads(Path('/run/readsb/aircraft.json').read_text());positions.append(dict(available=time.time(),now=a['now'],aircraft=[{k:r[k] for k in ('hex','lat','lon','seen_pos','nic','nac_p','mlat','tisb') if k in r} for r in a['aircraft'] if 'lat' in r]));lastpos=now
  if now-start>=35 and not owned and closed is None:
   assert not spool.active(),'Another consumer became active';spool.heartbeat();owned=True;lastheart=now
  if owned:
   if now-lastheart>1:spool.heartbeat();lastheart=now
   b=spool.take()
   if b and b.whole_raw is not None and len(cases)<8:
    name=f'rf-{len(cases):02d}.uc8';(D/name).write_bytes(b.whole_raw)
    cases.append(dict(file=name,epoch=b.epoch,first=b.first,wall=b.wall,queued=b.queued,sha256=hashlib.sha256(b.whole_raw).hexdigest(),bounds=b.bounds));print(json.dumps(dict(rf_seconds=len(cases))),flush=True)
    if len(cases)==8:closed=now
   if closed is not None and now-closed>8:break
  if now-start>80:raise RuntimeError('Capture deadline')
 if stop.is_set():raise RuntimeError('Capture interrupted')
 bases=[]
 for c in cases:
  b=spool.base(c['epoch'],c['first']);assert b is not None,'Missing production ledger';bases.append(b)
 assert live.count['stock_disconnects']==0
 after=health();assert before['pids']==after['pids'] and before['fr24_pid']==after['fr24_pid'] and before['configs']==after['configs']
 result=dict(cases=cases,base=bases,stock=list(stock.values()),relay=relay,positions=positions,before=before,after=after,errors=errors,evaluation_only=True,contains_iq=True)
 (D/'capture.private.json').write_text(json.dumps(result))
except BaseException as e:
 errors.append(repr(e));(D/'error.json').write_text(json.dumps(dict(errors=errors,cases=cases)));raise
finally:
 if owned:(spool.path/'enabled').unlink(missing_ok=True)
 stop.set();live.close();t.join(timeout=3)
 files=[p for p in D.iterdir() if p.is_file()];(D/'manifest.json').write_text(json.dumps({p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files},indent=2))

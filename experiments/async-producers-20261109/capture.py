"""Own an idle optional mirror briefly. No SDR, production outbox or flush ownership."""
import collections,hashlib,json,os,signal,socket,sys,threading,time,uuid
from pathlib import Path
from rescue.neural_spool import Spool
from rescue.shadow import LiveInput,valid_df17,CORRECTION_TICKS
from rescue.wire import BeastParser
from health import snapshot
D=Path(sys.argv[1]);assert str(D).startswith('/run/adsb-async-producers-');D.mkdir();spool=Spool('/run/adsb-rescue/neural');assert not spool.active(),'Mirror consumer active; do not interrupt'
before=snapshot();stop=threading.Event();live=LiveInput(D/'unused.sock',(0,0),indexed_stock_history=True);live.start(include_iq=False);cases=[];stock={};relay=[];positions=[];errors=[];owned=False;token=uuid.uuid4().hex.encode();marker=spool.path/'enabled';lastheart=0;lastpos=0;lasthealth=0;lastrefs=0;started=time.monotonic();closed=None;seen=set()
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
def receive():
 try:
  with socket.create_connection(('127.0.0.1',31005),timeout=2) as sock:
   sock.settimeout(.5);parser=BeastParser()
   while not stop.is_set():
    try:raw=sock.recv(65536)
    except socket.timeout:continue
    if not raw:raise RuntimeError('Relay closed')
    for r in parser.feed(raw):
     if valid_df17(r['message_hex']):relay.append(dict(ticks=r['ticks_12mhz']-CORRECTION_TICKS,message_hex=r['message_hex'],arrival=time.time()))
 except Exception as e:errors.append(repr(e));stop.set()
t=threading.Thread(target=receive);t.start()
try:
 while not stop.wait(.01):
  now=time.monotonic()
  if now-lastrefs>=.2:
   frames,_=live.snapshot()
   for r in frames:stock[(r['ticks'],r['message_hex'])]=r
   lastrefs=now
  if now-lastpos>=1:
   a=json.loads(Path('/run/readsb/aircraft.json').read_text());positions.append(dict(available=time.time(),now=a['now'],aircraft=[{k:v[k] for k in ['hex','lat','lon','seen_pos','nic','nac_p','mlat','tisb'] if k in v} for v in a['aircraft'] if 'lat' in v]));lastpos=now
  if now-lasthealth>=10:assert snapshot()==before,'Protected receiver changed';lasthealth=now
  if now-started>=35 and not owned:
   assert not spool.active() and not marker.exists(),'Another or stale mirror owner; refuse takeover'
   fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,token);os.close(fd);owned=True;lastheart=now;armed=time.time()
  if owned:
   assert marker.read_bytes()==token,'Mirror ownership changed'
   if now-lastheart>=1:os.utime(marker,None);lastheart=now
   for meta in sorted(spool.path.glob('batch-*.json')):
    if meta.name in seen:continue
    seen.add(meta.name)
    try:
     if meta.stat().st_mtime<armed:continue
     row=json.loads(meta.read_text())
     if not row['whole'] or len(cases)>=16:continue
     raw=(meta.parent/(meta.stem+'.whole.uc8')).read_bytes()
     assert len(raw)==4802400
     name=f'rf-{len(cases):02d}.uc8';(D/name).write_bytes(raw);cases.append(dict(file=name,epoch=row['epoch'],first=row['first'],wall=row['wall'],queued=row['queued'],sha256=hashlib.sha256(raw).hexdigest(),sample_count=len(raw)//2));print(json.dumps(dict(rf_seconds=len(cases))),flush=True)
     if len(cases)==16:closed=now
    except FileNotFoundError:raise RuntimeError('Mirror copy raced publisher; incomplete capture')
   if closed is not None and now-closed>=8:break
  if now-started>95:raise RuntimeError('Capture deadline')
 if stop.is_set():raise RuntimeError('Capture interrupted')
 bases=[spool.base(c['epoch'],c['first']) for c in cases];assert all(b is not None for b in bases),'Missing accepted-production ledger'
 assert len(cases)==16 and all(b['first']==a['first'] and b['epoch']==a['epoch'] for a,b in zip(cases,bases))
 assert len({c['epoch'] for c in cases})==1,'Receiver epoch changed'
 gaps=[dict(after=a['first'],before=b['first'],missing_samples=b['first']-a['first']-2400000) for a,b in zip(cases,cases[1:]) if b['first']-a['first']!=2400000]
 after=snapshot();assert after==before
 (D/'capture.private.json').write_text(json.dumps(dict(cases=cases,stock=list(stock.values()),relay=relay,base=bases,positions=positions,before=before,after=after,errors=errors,gaps=gaps,evaluation_only=True)))
except BaseException as e:
 errors.append(repr(e));(D/'error.json').write_text(json.dumps(dict(errors=errors,cases=cases)));raise
finally:
 if owned and marker.exists() and marker.read_bytes()==token:marker.unlink()
 stop.set();live.close();t.join(timeout=3)
 (D/'manifest.json').write_text(json.dumps({p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in D.iterdir() if p.is_file()},indent=2))

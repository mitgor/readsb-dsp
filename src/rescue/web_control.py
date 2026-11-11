"""Loopback-only, fixed-schema dashboard controls. No arbitrary commands."""
import argparse,hashlib,json,os,subprocess,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .pipeline import settings,DEFAULTS
from .relay_control import RelayControls
from .far_capture import config as capture_config
METHODS=tuple(DEFAULTS)+('sequence','acquisition')
class Controls:
 def __init__(self,base=Path('/etc/default'),restart=None,status=Path('/run/adsb-rescue/status.json')):
  self.paths=[base/'adsb-rescue.json',base/'adsb-rescue-workers.json',base/'adsb-far-capture.json'];self.restart=restart or self.system_restart;self.status=status;self.lock=threading.Lock();self.operation=dict(state='idle');self.relay=RelayControls(base=base,runtime=status.parent)
 def system_restart(self):
  began=time.time();subprocess.run(['systemctl','restart','adsb-rescue-shadow.service'],check=True,timeout=60)
  subprocess.run(['systemctl','is-active','--quiet','adsb-rescue-shadow.service'],check=True,timeout=5)
  for _ in range(60):
   try:
    state=json.loads(self.status.read_text())
    if state.get('started_unix',0)>=began-1 and state.get('threads_alive') and state.get('counts',{}).get('processed_seconds',0)>0:return
   except (OSError,ValueError):pass
   time.sleep(.5)
  raise RuntimeError('Decoder did not publish fresh healthy status')
 def revision(self):return hashlib.sha256(b'\0'.join(p.read_bytes() if p.exists() else b'' for p in self.paths)).hexdigest()
 def read(self):
  m=settings(self.paths[0]);w=json.loads(self.paths[1].read_text());c=capture_config(self.paths[2]);actual={}
  try:actual=json.loads(self.status.read_text()).get('method_switches',{})
  except (OSError,ValueError):pass
  feed_host=None
  try:
   for line in Path('/etc/fr24feed.ini').read_text().splitlines():
    if line.startswith('host='):feed_host=line.split('=',1)[1].strip().strip(chr(34))
  except OSError:pass
  return dict(fr24_input_host=feed_host,revision=self.revision(),methods={**m,'sequence':w.get('sequence_acquisition',False) and w.get('sequence_enabled',True),'acquisition':w.get('sequence_acquisition',False) and w.get('acquisition_enabled',True)},capture=c,actual_methods=actual,operation=self.operation)
 @staticmethod
 def atomic(path,data):
  tmp=path.with_suffix('.web-tmp');tmp.write_bytes(data);os.chmod(tmp,0o644);os.replace(tmp,path)
 def apply(self,data):
  with self.lock:
   if self.operation['state']=='applying' or self.relay.operation['state']=='applying':raise ValueError('An update is already in progress')
   if set(data)!= {'revision','methods','capture'} or data['revision']!=self.revision():raise ValueError('Settings changed; reload before applying')
   m=data['methods'];c=data['capture']
   if not isinstance(m,dict) or set(m)!=set(METHODS) or any(type(v) is not bool for v in m.values()) or not m['energy']:raise ValueError('Invalid methods; energy is required')
   if not isinstance(c,dict) or set(c)!={'packet_capture','continuous_capture'} or any(type(v) is not bool for v in c.values()):raise ValueError('Invalid capture switches')
   current=self.read()
   if m==current['methods'] and all(c[k]==current['capture'][k] for k in c):return current
   old=[p.read_bytes() if p.exists() else None for p in self.paths];w=json.loads(old[1]);changed=m!=current['methods']
   # Preserve every transport, CPU, native and FIR optimization in worker config.
   if (m['sequence'] or m['acquisition']) and not w.get('sequence_acquisition'):raise ValueError('Sequence/acquisition engine is unavailable')
   if m['pulse']:
    if not w.get('optimized_dsp') or not w.get('optimized_v3'):raise ValueError('C pulse filter requires optimized V3 DSP workers')
    root=Path('/home/pi/adsb-neural-rescue')
    model=root/'models/pulse-discriminant.json'
    if not model.exists() or hashlib.sha256(model.read_bytes()).hexdigest()!='bd9abaa59413fda4506ffb8c66f86418a7c33bc16b6c6d0521e42e904931b4fe':raise ValueError('C pulse model integrity check failed')
    if not (root/'src/rescue/_pulse_discriminant.so').exists():raise ValueError('C pulse kernel is unavailable')
   w.update(sequence_enabled=m['sequence'],acquisition_enabled=m['acquisition']);cap=capture_config(self.paths[2]);cap.update(c)
   new=[json.dumps({k:m[k] for k in DEFAULTS},indent=2).encode(),json.dumps(w,indent=2).encode(),json.dumps(cap,indent=2).encode()]
   try:
    for p,b in zip(self.paths,new):self.atomic(p,b)
   except Exception:
    for p,b in zip(self.paths,old):
     if b is not None:self.atomic(p,b)
     else:p.unlink(missing_ok=True)
    raise
   self.operation=dict(state='applying' if changed else 'complete',started_unix=time.time(),restarts=int(changed),error=None)
   if changed:
    def work():
     try:self.restart();self.operation.update(state='complete',finished_unix=time.time())
     except Exception as e:
      for p,b in zip(self.paths,old):
       if b is not None:self.atomic(p,b)
       else:p.unlink(missing_ok=True)
      try:self.restart();rollback='restored'
      except Exception:rollback='failed'
      self.operation.update(state='failed',error=str(e),rollback=rollback)
    threading.Thread(target=work,daemon=True).start()
   return self.read()
class Handler(BaseHTTPRequestHandler):
 def reply(self,n,data):
  b=json.dumps(data).encode();self.send_response(n);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  if self.path in ('/readsb-dsp/api/relay','/neural-rescue/api/relay'):
   try:self.reply(200,self.server.controls.relay.read())
   except Exception as e:self.reply(503,{'error':str(e)})
   return
  if self.path in ('/readsb-dsp/api/dashboard-status','/neural-rescue/api/dashboard-status'):
   try:
    from .dashboard_status import compact_status
    self.reply(200,compact_status(json.loads(self.server.controls.status.read_text())))
   except (OSError,ValueError):self.reply(503,{'error':'Receiver statistics unavailable'})
   return
  if self.path not in ('/readsb-dsp/api/settings','/neural-rescue/api/settings'):self.reply(404,{'error':'Unknown endpoint'});return
  try:self.reply(200,self.server.controls.read())
  except Exception as e:self.reply(500,{'error':str(e)})
 def do_POST(self):
  origin=urlsplit(self.headers.get('Origin',''));host=self.headers.get('Host','')
  if self.path not in ('/readsb-dsp/api/settings','/neural-rescue/api/settings','/readsb-dsp/api/relay','/neural-rescue/api/relay') or origin.scheme not in ('http','https') or origin.netloc!=host or self.headers.get('Content-Type','').split(';')[0]!='application/json':self.reply(403,{'error':'Same-origin JSON requests only'});return
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=8192:raise ValueError('Invalid request size')
   data=json.loads(self.rfile.read(n))
   with self.server.controls.lock:
    if self.path.endswith('/relay'):
     if self.server.controls.operation['state']=='applying':raise ValueError('Decoder settings are applying; wait before switching relay')
     result=self.server.controls.relay.apply(data)
    else:
     if self.server.controls.relay.operation['state']=='applying':raise ValueError('Relay mode is changing; wait before applying decoder settings')
     result=None
   if not self.path.endswith('/relay'):result=self.server.controls.apply(data)
   self.reply(200,result)
  except (ValueError,TypeError,KeyError) as e:self.reply(409,{'error':str(e)})
  except Exception as e:self.reply(500,{'error':str(e)})
 def log_message(self,*args):pass
 def setup(self):super().setup();self.connection.settimeout(5)
def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8911);a=p.parse_args();server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.controls=Controls();server.serve_forever()
if __name__=='__main__':main()

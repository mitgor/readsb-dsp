"""Fixed relay-mode control; production service changes use reviewed oneshot units."""
import hashlib,json,subprocess,threading,time
from pathlib import Path
MODES=('arrival_order','ordered_3s')
class RelayControls:
 def __init__(self,base=Path('/etc/default'),runtime=Path('/run/adsb-rescue'),state=Path('/var/lib/adsb-arrival-relay/active.json'),switch=None):
  self.config=base/'adsb-relay-arrival.json';self.native_config=base/'adsb-stream1090-lowlatency.json';self.runtime=runtime;self.state=state;self.switch=switch or self.system_switch;self.lock=threading.Lock();self.operation={'state':'idle'}
 @staticmethod
 def load(p):
  try:return json.loads(p.read_text())
  except FileNotFoundError:return {}
 @staticmethod
 def system_switch(mode):
  unit={'arrival_order':'adsb-relay-arrival-select.service','ordered_3s':'adsb-relay-ordered-select.service'}[mode]
  subprocess.run(['systemctl','start',unit],check=True,timeout=150)
 def read(self):
  cfg=self.load(self.config);feed=self.load(self.runtime/'feed-status.json');native=self.load(self.runtime/'status.json').get('lowlatency',{});guard=self.load(self.state);available=self.config.exists() and self.state.exists()
  return dict(available=available,revision=hashlib.sha256(self.config.read_bytes() if self.config.exists() else b'').hexdigest(),desired_mode='arrival_order' if cfg.get('enabled') else 'ordered_3s',actual_holdback_s=feed.get('holdback_s'),status_age_s=None if not feed else max(0,time.time()-feed.get('updated_unix',0)),native_backend=native.get('backend'),native_requested=bool(self.load(self.native_config).get('enabled')),guard_state=guard.get('state'),guard_reason=guard.get('reason'),operation=dict(self.operation))
 def apply(self,data):
  with self.lock:
   current=self.read()
   if not isinstance(data,dict) or set(data)!={'revision','mode'} or data['mode'] not in MODES:raise ValueError('Invalid relay mode request')
   if not current['available']:raise ValueError('Guarded relay selection is unavailable')
   if data['revision']!=current['revision']:raise ValueError('Relay mode changed; reload before applying')
   if self.operation['state']=='applying':raise ValueError('Relay selection already in progress')
   expected=0 if data['mode']=='arrival_order' else 3
   if current['desired_mode']==data['mode'] and current['actual_holdback_s']==expected and current['status_age_s'] is not None and current['status_age_s']<6:return current
   self.operation=dict(state='applying',mode=data['mode'],started_unix=time.time())
   def work():
    try:
     self.switch(data['mode']);actual=self.read()
     if actual['desired_mode']!=data['mode'] or actual['actual_holdback_s']!=expected or actual['status_age_s'] is None or actual['status_age_s']>=6:raise RuntimeError('Relay did not publish the selected mode')
     self.operation=dict(state='complete',mode=data['mode'],finished_unix=time.time())
    except Exception as exc:self.operation=dict(state='failed',mode=data['mode'],error=str(exc),finished_unix=time.time())
   threading.Thread(target=work,daemon=True).start();return self.read()

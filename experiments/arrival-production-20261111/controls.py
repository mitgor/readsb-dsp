"""Exercise rollback and two-strike behavior without receiver actions."""
import json,hashlib,runpy,tempfile
from pathlib import Path
from unittest.mock import patch

def main():
 with tempfile.TemporaryDirectory() as d:
  root=Path(d);backup=root/'backup';backup.mkdir();(backup/'feed.py').write_text('original')
  def read(p):return json.loads(Path(p).read_text())
  def save(p,v):Path(p).write_text(json.dumps(v))
  def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
  code=Path(__file__).with_name('mode.py').read_text()
  fake=dict(read=read,save=save,sha=sha,atomic=lambda p,b,rec:Path(p).write_bytes(b),STATE=root/'native-state',capture=lambda:None)
  scope={'__name__':'arrival_controls'}
  with patch('runpy.run_path',return_value=fake):exec(compile(code,'mode.py','exec'),scope)
  save(root/'native-state',dict(state='rolled_back'))
  calls=[];scope.update(ROOT=root,STATE=root/'state',CFG=root/'cfg',RUN=root/'run',ctl=lambda *args:calls.append(args),update_native_pid=lambda:None)
  p=root/'feed.py';p.write_text('candidate');st=dict(state='active',installed={'feed.py':sha(p)},original_feed_sha256=sha(backup/'feed.py'),backup=str(backup),boot='test')
  save(root/'state',st);scope['rollback']('test');assert p.read_text()=='original' and not read(root/'cfg')['enabled'] and calls==[('restart','adsb-rescue-feed')]
  p.write_text('concurrent');save(root/'state',st);scope['rollback']('test');assert p.read_text()=='concurrent' and read(root/'state')['state']=='rollback_conflict'
  p.write_text('candidate');save(root/'state',st);scope['check']=lambda *_:(_ for _ in ()).throw(RuntimeError('test health fault'))
  original=Path.read_text
  def read_text(path,*a,**kw):return 'test' if str(path)=='/proc/sys/kernel/random/boot_id' else original(path,*a,**kw)
  with patch.object(Path,'read_text',read_text):
   scope['guard']();assert read(root/'state')['bad_checks']==1 and read(root/'state')['state']=='active'
   scope['guard']();assert read(root/'state')['state']=='rolled_back'
  import time
  save(root/'state',st);save(root/'native-state',dict(state='activating',deadline=time.time()+60));scope['ready']=lambda:dict(stock_connected=True)
  scope['guard']();assert read(root/'state')['state']=='active' and read(root/'run')['state']=='waiting_for_authorized_native_startup'
 print('Arrival rollback, source-conflict, two-strike and bounded startup controls passed')
if __name__=='__main__':main()

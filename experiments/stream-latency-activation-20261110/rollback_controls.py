"""Test rollback on owned temporary files with all service operations mocked."""
import hashlib,json,tempfile,time
from pathlib import Path
from unittest.mock import patch

def main():
 d=Path(__file__).with_name('deploy.py').read_text()
 with tempfile.TemporaryDirectory() as name:
  r=Path(name);calls=[]
  def read(p):return json.loads(Path(p).read_text())
  def save(p,v):Path(p).write_text(json.dumps(v))
  def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
  def atomic(p,b,_):Path(p).write_bytes(b)
  def snapshot():return dict(threads_alive=True,updated_unix=time.time())
  fake=dict(read=read,save=save,sha=sha,atomic=atomic,boot=lambda:'boot',snapshot=snapshot,healthy=lambda *_:None,capacity=lambda *_:None)
  scope={'__name__':'rollback_control'}
  with patch('runpy.run_path',return_value=fake):exec(compile(d,'deploy.py','exec'),scope)
  scope.update(ROOT=r,STATE=r/'state',CFG=r/'config',RUN=r/'run',restart=lambda:calls.append('restart'))
  b=r/'backup';b.mkdir();old=b/'shadow.py';old.write_bytes(b'original');live=r/'shadow.py'
  save(b/'original.json',dict(sha256=sha(old)));state=dict(state='active',backup=str(b),boot='boot',before={},installed={})
  def setup():
   live.write_bytes(b'candidate');state['installed'][str(live)]=sha(live);save(r/'state',state);save(r/'config',dict(enabled=True))
  setup();scope['rollback']('test');assert live.read_bytes()==b'original' and not read(r/'config')['enabled'] and read(r/'state')['state']=='rolled_back' and not calls
  setup();live.write_bytes(b'concurrent edit');scope['rollback']('test');assert live.read_bytes()==b'concurrent edit' and read(r/'state')['state']=='rollback_conflict'
  setup();scope['check']=lambda *_:(_ for _ in ()).throw(RuntimeError('test fault'));scope['guard']();assert read(r/'state')['state']=='active' and read(r/'state')['bad_checks']==1;scope['guard']();assert read(r/'state')['state']=='rolled_back' and live.read_bytes()==b'original' and not calls
 # Exercise actual checkpoint relocation: continue must not starve liveness.
 import runpy
 move=runpy.run_path(str(Path(__file__).with_name('patch.py')))['status_checkpoint']
 block="            if True:\n                writes.append('status')\n"
 source="def run(stop,writes):\n    try:\n        while not stop.is_set():\n            # A bounded worker loop\n            continue\n"+block+"    finally:pass\n"
 class Stop:
  def __init__(self):self.n=0
  def is_set(self):self.n+=1;return self.n>2
 old={};exec(source,old);writes=[];old['run'](Stop(),writes);assert not writes
 changed={};exec(move(source,block),changed);changed['run'](Stop(),writes);assert writes==['status','status']
 print('Three rollback and continue-safe status checkpoint controls passed')
if __name__=='__main__':main()

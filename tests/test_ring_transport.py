import multiprocessing as mp,tempfile,time,unittest
from pathlib import Path
import numpy as np
from rescue.ring_transport import FrontendRing,RingStreamingPool,MAX_IQ
from rescue.pipeline import settings
from rescue.streaming import Assembler,TOTAL

def publish_child(r,slot,gen):
 iq=np.arange(500,dtype=np.float32).astype(np.complex64);r.publish(slot,gen,0,0,20,iq,np.ones(500,np.float32),np.zeros(469,np.float64))

def coherent_worker_options():
 from rescue import workers
 d=workers._DECODER
 return d.decoder.pair_retry,any(c.__name__=='ExtendedNeonBackend' for c in type(d.backend).__mro__),d.backend.role

def pulse_worker_options():
 from rescue import workers
 d=workers._DECODER
 return d.pulse_model['schema'],d.optimized_backend.role

class RingTests(unittest.TestCase):
 def test_optional_c_pulse_loads_in_shared_ring_worker(self):
  import os
  cpus=sorted(os.sched_getaffinity(0))[:4] if hasattr(os,'sched_getaffinity') else [0,1,2,3]
  if len(cpus)<4:self.skipTest('Four worker affinity CPUs needed')
  selection=dict(workers=2,worker_cpus=cpus[2:],coherent_cpus=cpus[:2],config=dict(optimized_dsp=True,optimized_v3=True,sequence_acquisition=True,sequence_enabled=True,cached_fir=True))
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as tmp:
   pool=RingStreamingPool(root/'models/tiny-fp32.onnx',{**settings(),'coherent':True,'pulse':True},Path(tmp),selection)
   try:self.assertEqual(pool.executor.submit(pulse_worker_options).result(timeout=30),('pulse-discriminant-v1','producer'))
   finally:pool.close()
 def test_optional_coherent_flags_reach_ring_worker(self):
  import os
  cpus=sorted(os.sched_getaffinity(0))[:4] if hasattr(os,'sched_getaffinity') else [0,1,2,3]
  if len(cpus)<4:self.skipTest('Four worker affinity CPUs needed')
  selection=dict(workers=2,worker_cpus=cpus[2:],coherent_cpus=cpus[:2],config=dict(optimized_dsp=True,optimized_v3=True,sequence_acquisition=True,sequence_enabled=True,cached_fir=True,optimized_extended=True,coherent_pair_retry=True))
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as tmp:
   pool=RingStreamingPool(root/'models/tiny-fp32.onnx',{**settings(),'coherent':True},Path(tmp),selection)
   try:self.assertEqual(pool.coherent_executor.submit(coherent_worker_options).result(timeout=30),(True,True,'consumer'))
   finally:pool.close()
 def test_capacity_generation_reuse_and_ownership(self):
  r=FrontendRing(1);slot,gen=r.acquire(b'\x7f\x80'*100,0,2)
  with self.assertRaises(RuntimeError):r.acquire(b'xx',0,1)
  self.assertFalse(r.raw(slot,gen).flags.writeable)
  r.release(slot,gen);s,g=r.acquire(b'xx',0,1);self.assertEqual(s,slot);self.assertGreater(g,gen)
  with self.assertRaises(RuntimeError):r.release(slot,gen)
  with self.assertRaises(RuntimeError):r.raw(slot,gen)
  self.assertEqual(r.active(),1);r.release(s,g);self.assertEqual(r.active(),0)
 def test_spawn_publication_and_timeout(self):
  r=FrontendRing(1);s,g=r.acquire(b'xx',0,1)
  with self.assertRaises(TimeoutError):r.consume(s,g,0,0,20,500,timeout=.01)
  p=mp.get_context('spawn').Process(target=publish_child,args=(r,s,g));p.start();iq,power,score=r.consume(s,g,0,0,20,500,timeout=90);p.join(90);self.assertEqual(p.exitcode,0)
  np.testing.assert_array_equal(iq,np.arange(500));self.assertFalse(iq.flags.writeable)
  with self.assertRaises(ValueError):r.consume(s,g,0,1,20,500,timeout=.01)
  r.release(s,g)
 def test_slow_consumer_stale_event_cannot_satisfy_new_generation(self):
  r=FrontendRing(1);s,g=r.acquire(b'xx',0,1);publish_child(r,s,g);r.release(s,g);_,g2=r.acquire(b'xx',0,1)
  with self.assertRaises(TimeoutError):r.consume(s,g2,0,0,20,500,timeout=.01)
  with self.assertRaises(RuntimeError):publish_child(r,s,g)
  r.release(s,g2)
 def test_wraparound_and_missing_producer_are_bounded(self):
  r=FrontendRing(2);size=len(r.data)
  for j in range(100):
   s,g=r.acquire(b'xx'*(1+j%7),0,1);publish_child(r,s,g);r.consume(s,g,0,0,20,500,timeout=.01);r.release(s,g)
  self.assertEqual(len(r.data),size);self.assertEqual(r.active(),0)
  s,g=r.acquire(b'xx',0,1)
  p=mp.get_context('spawn').Process(target=time.sleep,args=(.01,));p.start();p.join(10)
  with self.assertRaises(TimeoutError):r.consume(s,g,0,0,20,500,timeout=.02)
  r.release(s,g)
 def test_worker_death_releases_only_after_pool_shutdown(self):
  import os
  cpus=sorted(os.sched_getaffinity(0))[:4] if hasattr(os,'sched_getaffinity') else [0,1,2,3]
  if len(cpus)<4:self.skipTest('Four worker affinity CPUs needed')
  selection=dict(workers=2,worker_cpus=cpus[2:],coherent_cpus=cpus[:2],config=dict(optimized_dsp=True,optimized_v3=True,sequence_acquisition=True,sequence_enabled=False))
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as tmp:
   pool=RingStreamingPool(root/'models/tiny-fp32.onnx',{**settings(),'coherent':True},Path(tmp),selection,settle_s=0)
   try:
    batch=Assembler(100).feed(1,0,0,bytes([127,128])*TOTAL)[0];pool.submit(batch)
    list(pool.executor._processes.values())[0].terminate()
    self.assertEqual(pool.ring.active(),1)
   finally:pool.close()
   self.assertEqual(pool.ring.active(),0);self.assertFalse(list(Path(tmp).iterdir()))
 def test_actual_stream_exact_and_no_transport_files(self):
  from rescue.streaming import StreamingPool
  import os
  cpus=sorted(os.sched_getaffinity(0))[:4] if hasattr(os,'sched_getaffinity') else [0,1,2,3]
  if len(cpus)<4:self.skipTest('Four worker affinity CPUs needed')
  selection=dict(workers=2,worker_cpus=cpus[2:],coherent_cpus=cpus[:2],config=dict(optimized_dsp=True,optimized_v3=True,sequence_acquisition=True,sequence_enabled=False,coherent_threshold=.35,coherent_budget=48))
  root=Path(__file__).resolve().parents[1];raw=np.random.default_rng(97).integers(110,145,TOTAL*2,dtype=np.uint8).tobytes();outputs=[]
  with tempfile.TemporaryDirectory() as tmp:
   for cls in (StreamingPool,RingStreamingPool):
    pool=cls(root/'models/tiny-fp32.onnx',{**settings(),'coherent':True},Path(tmp),selection,settle_s=0)
    try:
     batches=Assembler(100).feed(1,0,0,raw);i=0;result=None;deadline=time.monotonic()+240
     while result is None and time.monotonic()<deadline:
      while i<len(batches) and len(pool.pending)<pool.max_pending_jobs:pool.submit(batches[i]);i+=1
      result=pool.pop();time.sleep(.001)
     self.assertIsNotNone(result);self.assertEqual(result[0][3],raw)
     outputs.append(result[1]);self.assertEqual(pool.report()['completed_rf_seconds'],1)
     if cls is RingStreamingPool:self.assertEqual(pool.ring.active(),0)
    finally:pool.close()
    self.assertFalse(list(Path(tmp).iterdir()))
  self.assertEqual(outputs[0],outputs[1])

 def test_transport_config_and_factory(self):
  import json
  from unittest.mock import patch
  from rescue.workers import plan
  from rescue.streaming import make_streaming_pool
  info=dict(logical_cpus=[0,1,2,3],performance_cpus=[0,1,2,3],classification_verified=True)
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'cfg';path.write_text(json.dumps(dict(shared_transport='ring')))
   with self.assertRaises(ValueError):plan(path,info)
   cfg=dict(shared_transport='ring',optimized_dsp=True,optimized_v3=True,sequence_acquisition=True,sequence_enabled=False,cpus='2-3',coherent_cpus='0-1')
   path.write_text(json.dumps(cfg));self.assertEqual(plan(path,info)['config']['shared_transport'],'ring')
  with patch('rescue.ring_transport.RingStreamingPool',return_value='ring') as ring:
   self.assertEqual(make_streaming_pool('m',{},'r',dict(config=cfg)),'ring');ring.assert_called_once()
  with patch('rescue.streaming.StreamingPool',return_value='files') as files:
   self.assertEqual(make_streaming_pool('m',{},'r',dict(config={})),'files');files.assert_called_once()

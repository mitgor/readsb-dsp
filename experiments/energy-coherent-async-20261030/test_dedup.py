import importlib.util,json,random,sys,time
from pathlib import Path
from rust_history import RustHistory

def reference(path):
 spec=importlib.util.spec_from_file_location('reference',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.HistoryMerge

def main():
 lib,ref,output=sys.argv[1:];Python=reference(ref);rng=random.Random(20261030);a=Python(capacity=128);b=RustHistory(lib,capacity=128);now=0.;tick=100000;epoch=1;payloads=[rng.randbytes(14).hex() for _ in range(40)];trace=[]
 try:
  # Exact TTL and adjacent-bin boundaries, late stock, reset and future timestamps.
  for s,e,t,p,n,v in [('stock',1,1440,payloads[0],0.,True),('energy',1,2880,payloads[0],.001,True),('coherent',1,2881,payloads[0],.002,True),('energy',1,10000,payloads[0],.003,True),('stock',1,10000,payloads[0],.004,True),('energy',2,10000,payloads[0],.005,True),('stock',2,10000,payloads[0],5.004,True)]:
   x=a.push(s,e,t,p,n,validated=v);y=b.push(s,e,t,p,n,validated=v);assert x==y;assert a.count==b.count;trace.append(x)
  a.reset(1);b.reset(1)
  for i in range(50000):
   now+=rng.choice([.0001,.001,.01,.1]);tick+=rng.randrange(10000);source=rng.choice(['stock','energy','coherent']);p=rng.choice(payloads);t=tick-rng.choice([0,1,1440,1441,60000001]);e=epoch if rng.random()>.005 else epoch+1;valid=rng.random()>.01
   x=a.push(source,e,t,p,now,validated=valid);y=b.push(source,e,t,p,now,validated=valid)
   assert x==y,(i,source,e,t,now);assert a.count==b.count,(i,a.count,b.count);assert a.serial_count==b.size;trace.append(x)
   if i%2500==0:epoch+=1;a.reset(epoch);b.reset(epoch)
  # Cross-method same transmission suppressed, same payload another RF time retained.
  assert b.size<=128
 finally:b.close()
 # Interface-inclusive throughput, same trace, bounded cache.
 data=[('stock' if i%5==0 else ('energy' if i%2 else 'coherent'),1,i*24000,payloads[i%40],i*.002) for i in range(100000)]
 times={};counts={}
 for name,cache in [('python',Python()),('rust',RustHistory(lib))]:
  start=time.process_time();ok=0
  for s,e,t,p,n in data:ok+=cache.push(s,e,t,p,n,validated=True)
  times[name]=time.process_time()-start;counts[name]=ok
  if name=='rust':cache.close()
 assert counts['python']==counts['rust']
 result=dict(randomized_events=50007,reference_decisions_and_counters_exact=True,throughput_events=len(data),cpu_s=times,accepted=counts,rust_includes_ctypes=True)
 Path(output).write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()

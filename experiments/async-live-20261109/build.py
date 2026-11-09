"""Build additive modules against an exact current production shadow snapshot."""
from pathlib import Path
import argparse,json,hashlib
H=Path(__file__).resolve().parent;R=H.parents[1]
def build(shadow,dest):
 dest.mkdir(parents=True,exist_ok=False)
 def put(name,code):(dest/('async_live_'+name+'.py')).write_text(code)
 put('completion',(R/'experiments/async-native-20261109/completion.py').read_text())
 put('dedup',(R/'experiments/async-relay-20261030/dedup.py').read_text())
 old=(R/'experiments/latency-publication-20261030/prototype.py').read_text();start=old.index('class ImmediateRelay');immediate='from .feed import Relay,beast,valid,unwrap,MOD,CORRECTION,ALLOWED\n'+old[start:];immediate=immediate.replace("out.append(wire)","\n            if source!='stock':self.count['relayed_'+source]+=1\n            out.append(wire)");put('immediate',immediate)
 old=(R/'experiments/async-native-20261109/integration.py').read_text();put('admission','from collections import Counter,deque\nfrom .shadow import evaluate\nfrom .streaming import HALO,CORE\nSOURCES=frozenset((\'energy\',\'timing\',\'soft\',\'matched\',\'coherent\',\'sequence\',\'acquisition\',\'header\',\'sic\',\'neural\',\'pulse\',\'stream1090\'))\n'+old[old.index('class Admission:'):])
 put('engine',(H/'engine.py').read_text());put('feed',(H/'relay.py').read_text())
 s=shadow.read_text()
 def replace(old,new):
  nonlocal s
  assert s.count(old)==1,(old,s.count(old));s=s.replace(old,new)
 replace('    pool=make_streaming_pool(model,methods,a.runtime,selection,dispatch_ms=a.dispatch_ms)', '''    from .async_live_completion import CompletionPool
    from .ring_transport import RingStreamingPool
    class Tapped(CompletionPool,RingStreamingPool):pass
    pool=Tapped(model,methods,a.runtime,selection,dispatch_ms=a.dispatch_ms)''')
 replace("    live.start();modelsha=", "    from .async_live_engine import Engine\n    engine=Engine(live,a.runtime/'feed-outbox',{**methods,'sequence':selection['config']['sequence_enabled'],'acquisition':selection['config']['acquisition_enabled']},a.stream1090_binary)\n    live.start();modelsha=")
 replace("return {'method_metrics':metrics", "return {'async_output':engine.report(),'method_metrics':metrics")
 replace('                        pool.submit(item,references)', '                        engine.begin(item)\n                        pool.submit(item,references)')
 replace('            result=pool.pop()', '            result=pool.pop()\n            for batch,rows,detail in pool.take_completed():engine.offer(batch,rows,detail)\n            engine.tick()\n            result=engine.grouped(result)')
 a=s.index('                if stream1090:\n                    # Keep');b=s.index('                corrected=',a)
 s=s[:a]+'''                # Stream1090 runs independently; grouping is statistics only.
                if engine.stream:
                    candidates.extend(engine.rows.get((epoch,first),()))
                    stream1090=engine.stream
'''+s[b:]
 a=s.index("                outbox=a.runtime/'feed-outbox'");b=s.index('                primary=',a)
 s=s[:a]+'''                # Producer completion engine alone publishes relay outbox rows.
'''+s[b:]
 replace('        live.close();pool.close();archive.flush(status(),force=True)', '        engine.close();live.close();pool.close();archive.flush(status(),force=True)')
 put('shadow',s)
 (dest/'manifest.json').write_text(json.dumps(dict(base_shadow_sha256=hashlib.sha256(shadow.read_bytes()).hexdigest(),files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.glob('*.py')}),indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--shadow',type=Path,required=True);p.add_argument('--dest',type=Path,required=True);a=p.parse_args();build(a.shadow,a.dest)

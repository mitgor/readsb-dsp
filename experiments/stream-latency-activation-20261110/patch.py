"""Minimal production hookup, applicable to the current deployed coordinator."""
def patch(source):
 def replace(a,b):
  nonlocal source
  if source.count(a)!=1:raise ValueError('Unexpected coordinator source anchor: '+a[:70])
  source=source.replace(a,b)
 replace("self.path=Path(sockpath);self.origin", "self.low_latency=None;self.path=Path(sockpath);self.origin")
 replace('            before=assembler.discontinuities', '            if self.low_latency:self.low_latency.offer_iq(pid,sample,packet[HEADER.size:])\n            before=assembler.discontinuities')
 replace("                                self.frames.append({**frame,'ticks':frame['ticks_12mhz']-CORRECTION_TICKS,'arrival':now})", "                                stock_row={**frame,'ticks':frame['ticks_12mhz']-CORRECTION_TICKS,'arrival':now}\n                                self.frames.append(stock_row)\n                                if self.low_latency:self.low_latency.offer_stock(stock_row)")
 replace('    live.start();modelsha=', "    from .lowlatency_stream import configured,CompletionTap\n    low=configured(live,methods,a.runtime);tap=CompletionTap(pool) if low is not None else None;live.low_latency=low\n    live.start();modelsha=")
 replace("'stream1090':stream1090.report() if stream1090 else {'enabled':False}","'lowlatency':low.report() if low is not None else {'enabled':False},'stream1090':low.report() if low is not None and not low.failed else (stream1090.report() if stream1090 else {'enabled':False})")
 replace('            result=pool.pop()',"            result=tap.pop() if tap is not None else pool.pop()\n            if low is not None:\n                low.tick()\n                for batch,rows,detail in tap.take():low.offer_completion(batch,rows,detail)\n                low.tick()")
 replace('                        stream_events,cpu_s=stream1090.decode(raw,first,frames)', "                        stream_events,cpu_s=low.stream_rows(first,epoch) if low is not None and not low.failed else (None,0.)\n                        if stream_events is None:stream_events,cpu_s=stream1090.decode(raw,first,frames)")
 replace('        live.close();pool.close();archive.flush(status(),force=True)', '        live.close();pool.close();archive.flush(status(),force=True)\n        if low is not None:low.close()')
 return source
if __name__=='__main__':
 import sys
 from pathlib import Path
 Path(sys.argv[2]).write_text(patch(Path(sys.argv[1]).read_text()))

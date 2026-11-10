"""Synthetic admission/relay controls. Outputs remain inside anonymous test sockets."""
import argparse,json
from pathlib import Path
from bridge import Bridge
from final import Final,RustCache
from rescue.stock_history import StockHistory
from rescue.shadow import valid_df17

def payload(i,icao=0xabcdef):
 v=(0x8d<<104)|(icao<<80)|(i<<24);r=v
 for bit in range(111,23,-1):
  if r&(1<<bit):r^=0x1fff409<<(bit-24)
 p=f'{v|r:028x}';assert valid_df17(p);return p

def main():
 p=argparse.ArgumentParser();p.add_argument('--dedup',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();checks=[];first=20000000;start=(first+600)*5;end=start+12000000;epoch=7;c={'first':first};target=payload(900);t=start+300000;anchors=[dict(source='energy',ticks=start+i*10000,message_hex=payload(i+1)) for i in range(20)];history=StockHistory()
 for r in anchors:history.append(r)
 history.append(dict(ticks=end+2000,message_hex=payload(901,0x123456)))
 frames=history.snapshot();native=[(r['ticks']+1631,r['message_hex']) for r in anchors]+[(t+1631,target)];emitted=[];b=Bridge(epoch,lambda *x:emitted.append(x));b.begin(0,c)
 b.offer(0,'native',epoch,native,end+2000,False);b.offer(0,'energy',epoch,anchors,end+2000,False)
 b.drain([],end+2000,0);assert not emitted;checks.append('future_stock_cannot_authorize')
 b.drain(frames,end+2000,0);assert any(r[0]['message_hex']==target for r in emitted);checks.append('causal_stock_energy_and_clock_admission')
 emitted=[];b=Bridge(epoch,lambda *x:emitted.append(x));b.begin(0,c);b.offer(0,'native',epoch,native,end+2000,False);b.drain(frames,end+2000,0);assert not emitted;checks.append('missing_energy_watermark_blocks_early')
 b.offer(0,'energy',epoch+1,anchors,end+2000,True);assert not b.energy;checks.append('old_epoch_rejected')
 try:b.offer(0,'native',epoch,[(t,'8d'+'00'*13)],end,False);raise AssertionError('Bad CRC accepted')
 except ValueError:checks.append('invalid_CRC_rejected')
 # Evidence late in a logical window is permitted only through the explicit final lane.
 emitted=[];b=Bridge(epoch,lambda *x:emitted.append(x),early=False);b.begin(0,c);b.offer(0,'native',epoch,native,end+2000,True);b.offer(0,'energy',epoch,anchors,end+2000,True);b.drain(frames,end+2000,1);assert any(x[0]['message_hex']==target and x[3]=='final' for x in emitted);checks.append('batch_finalization_fallback')
 # Final stage independently enforces causal ICAO/conflict/age guards.
 final=Final(a.dedup,epoch);final.history=history;audit=dict(verified=True,matches=20,median_abs_error_us=0)
 stock=dict(ticks=end+2000,ticks_12mhz=end+2000+2398,message_hex=payload(901,0x123456),signal_byte=26,arrival=0)
 final.stock(stock,100,False);r=dict(source='stream1090',ticks=t,message_hex=target);final.extra(r,audit,.1,'early');final.extra(dict(r,source='energy'),audit,.1,'early');assert final.count['emitted_early']==1;checks.append('shared_cross_method_dedup')
 final.extra(dict(r,ticks=t+10000),audit,.2,'early');assert final.count['emitted_early']==2;checks.append('same_payload_new_transmission_retained')
 final.extra(dict(r,message_hex=payload(1,0x888888)),audit,.2,'early');assert final.count['relay_no_prior_stock']==1;checks.append('no_prior_stock_rejected')
 history.append(dict(ticks=t+2,message_hex=payload(902)));final.extra(r,audit,.2,'early');assert final.count['relay_stock_conflict']==1;checks.append('stock_conflict_rejected')
 final.stock(dict(stock,ticks=t,ticks_12mhz=t+2398,message_hex=target),100.3,False);counts=final.close();assert counts['late_stock_after_extra_race']==1;checks.append('late_stock_preserved_and_race_counted')
 cache=RustCache(a.dedup,epoch);assert cache.push(0,t,target,100);assert not cache.push(1,t+10000,target,100.1,False);assert cache.counts()['unvalidated']==1;cache.close();checks.append('Rust_unvalidated_extra_rejected')
 a.output.write_text(json.dumps(dict(passed=checks,all_passed=True,production_actions=[]),indent=2)+'\n');print('Passed',len(checks),'controls')
if __name__=='__main__':main()

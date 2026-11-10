"""Parity/negative controls for the isolated Rust admission engine."""
import argparse,collections,hashlib,json,random,time
from pathlib import Path
import numpy as np
from native_admission import NativeAdmission,SOURCES
from rescue.shadow import evaluate,valid_df17
from rescue.stock_history import StockHistory

def payload(n,icao=0xabcdef):
 v=(0x8d<<104)|(icao<<80)|(n<<24);r=v
 for bit in range(111,23,-1):
  if r&(1<<bit):r^=0x1fff409<<(bit-24)
 p=f'{v|r:028x}';assert valid_df17(p);return p

def main():
 p=argparse.ArgumentParser();p.add_argument('--library',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--capture',type=Path);a=p.parse_args();assert not a.output.exists();checks=[];comparisons=0
 def check(engine,stock,candidates):
  nonlocal comparisons
  expected=evaluate(stock.snapshot(),candidates,0,2**62);actual=engine.evaluate(candidates,0,2**62);assert actual==expected,(actual,expected);comparisons+=1;return actual
 start=1_000_000_000;anchors=[dict(source='energy',ticks=start+i*10000,message_hex=payload(i+1)) for i in range(20)]
 with NativeAdmission(a.library,epoch=7) as engine:
  stock=StockHistory()
  assert engine.latest_stock_tick is None
  check(engine,stock,[]);check(engine,stock,anchors)
  for r in anchors:
   stock.append(r);engine.append_stock(r);check(engine,stock,anchors)
  t=start+500000;p200=payload(200);candidates=anchors+[dict(source=s,ticks=t,message_hex=p200,metadata=s) for s in reversed(SOURCES)]
  result=check(engine,stock,candidates);assert len(result[0])==1 and result[0][0]['source']=='energy';checks.append('all_12_source_priorities_and_stable_rows')
  result=check(engine,stock,anchors+[dict(source='stream1090',ticks=t,message_hex=p200),dict(source='energy',ticks=t+1440,message_hex=p200),dict(source='neural',ticks=t+1441,message_hex=p200),dict(source='neural',ticks=t+2881,message_hex=p200)])
  assert any(r['ticks']==t+2881 for r in result[0]);checks.append('120us_boundaries_and_neural_energy_guard')
  invalid=f'{int(p200,16)^1:028x}';check(engine,stock,anchors+[dict(source='stream1090',ticks=t,message_hex=x) for x in [invalid,'xyz','',p200[:-2]]]+[dict(source='unknown',ticks=t,message_hex=p200)]);checks.append('CRC_format_unknown_source_rejection')
  result=check(engine,stock,anchors+[dict(source='stream1090',ticks=t,message_hex=payload(300,0x123456))]);assert result[2]['no_prior_stock_icao']==1;checks.append('stock_only_prior_identity')
  conflict=dict(source='energy',ticks=t+48,message_hex=payload(301));stock.append(conflict);engine.append_stock(conflict);result=check(engine,stock,anchors+[dict(source='stream1090',ticks=t,message_hex=p200)]);assert result[2]['stock_conflict']==1;checks.append('48tick_stock_conflict_boundary')
  check(engine,stock,[dict(r,ticks=r['ticks']+24+(i%2)) for i,r in enumerate(anchors)]);checks.append('even_median_exact_half_tick_and_alignment_rejection')
  check(engine,stock,[dict(r,ticks=r['ticks']+24) for r in anchors]);checks.append('24tick_alignment_acceptance_boundary')
  check(engine,stock,[dict(r,ticks=r['ticks']+1440.25,source='timing') for r in anchors]+anchors);checks.append('exact_quarter_tick_fractional_DSP_boundary')
  check(engine,stock,[dict(source='unknown')]);checks.append('unknown_source_does_not_parse_unused_fields')
  try:engine.evaluate([dict(source='stream1090',ticks=t+.1,message_hex=p200)],0,2**62);raise AssertionError('Inexact timestamp accepted')
  except ValueError:checks.append('inexact_timestamp_fails_closed_without_rounding')
  engine.reset(8);assert len(engine)==0 and engine.latest_stock_tick is None;check(engine,StockHistory(),anchors);checks.append('epoch_reset_clears_stock_evidence')
 # Encoding cache must never cache an admission decision or mutable row dict.
 with NativeAdmission(a.library,epoch=1) as engine:
  stock=StockHistory();candidate=dict(source='stream1090',ticks=start+500000,message_hex=payload(500),metadata='first')
  check(engine,stock,anchors+[candidate])
  for r in anchors:stock.append(r);engine.append_stock(r)
  result=check(engine,stock,anchors+[candidate]);assert result[0][-1] is candidate
  encoded=engine._prepare(candidate);changed=dict(candidate,metadata='second');assert engine._prepare(changed) is encoded;result=check(engine,stock,anchors+[changed]);assert result[0][-1] is changed and result[0][-1]['metadata']=='second'
  engine._row_cache_limit=5;engine._row_cache.clear();check(engine,stock,anchors+[changed]);assert len(engine._row_cache)<=5
  engine.reset(2);assert not engine._row_cache;check(engine,StockHistory(),anchors+[changed]);checks.append('bounded_immutable_encoding_cache_not_admission_or_metadata_cache')
 # Bounded arrival eviction and RF ordering must be identical to StockHistory.
 rng=random.Random(81110)
 with NativeAdmission(a.library,maxlen=23,epoch=1) as engine:
  stock=StockHistory(maxlen=23);all_seen=[]
  for iteration in range(120):
   r=dict(ticks=start+rng.randrange(100)*10000,message_hex=payload(rng.randrange(1,80),0xabc000+rng.randrange(4)));stock.append(r);engine.append_stock(r);all_seen.append(r['ticks']);assert len(engine)==len(stock)<=23;assert engine.latest_stock_tick==max(all_seen)
   cand=[dict(source='energy',ticks=s['ticks']+rng.choice([0,1,-1,24,25]),message_hex=s['message_hex']) for s in stock]
   cand.extend(dict(source=rng.choice(SOURCES),ticks=start+rng.randrange(100)*10000,message_hex=payload(rng.randrange(1,80),0xabc000+rng.randrange(6))) for _ in range(25));rng.shuffle(cand);check(engine,stock,cand)
 checks.append('bounded_arrival_eviction_out_of_order_RF_and_randomized_parity')
 # Same-transmission historical I/Q energy, not stock-derived fabricated anchors.
 historical=None
 if a.capture:
  from rescue.fir_cached import FirBackend
  from rescue.dsp import features,baseline,payloads,crc_batch,SAMPLES
  data=json.loads((a.capture/'capture.private.json').read_text());assert not data['errors'];backend=FirBackend();stock=StockHistory();engine=NativeAdmission(a.library,epoch=data['cases'][0]['epoch']);rows=sorted(data['stock'],key=lambda r:r['arrival']);pointer=0;calls=0
  for c in data['cases']:
   path=a.capture/c['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==c['sha256'];energy=[]
   for offset,core,iq in backend.iq_blocks(path,.05):
    starts,_=backend.candidate_scores(iq,core,.4);starts=starts[backend.header_ids(iq,starts)]
    for n in range(0,len(starts),512):
     pos=starts[n:n+512];pred=payloads(baseline(features(iq[pos[:,None]+np.arange(SAMPLES)[None,:]])));valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
     energy += [dict(source='energy',ticks=c['first']*5+(offset+int(at))*3,message_hex=bytes(msg).hex()) for at,msg in zip(pos[valid],pred[valid])]
    # Causal stock availability at the end of each existing 50 ms block.
    available=c['wall']+(offset*3/5+core*3/5+600)/2400000
    while pointer<len(rows) and rows[pointer]['arrival']<=available:
     r=rows[pointer];stock.append(r);engine.append_stock(r);pointer+=1
    check(engine,stock,energy);calls+=1
   # The actual producer journal has no individual completion times. Its rows
   # enter only the explicit deferred parity check, not a latency claim.
   while pointer<len(rows) and rows[pointer]['arrival']<=c['wall']+1.5:
    r=rows[pointer];stock.append(r);engine.append_stock(r);pointer+=1
   extras=[r for b in data['base'] if b['first']==c['first'] for r in b['extra']];check(engine,stock,energy+extras);calls+=1
  engine.close();historical=dict(windows=len(data['cases']),parity_calls=calls,source='Actual same-RF energy frontend plus recorded complete producer rows in deferred checks; no training labels or pipeline output',capture_sha256=hashlib.sha256((a.capture/'capture.private.json').read_bytes()).hexdigest());checks.append('historical_actual_RF_energy_and_recorded_producer_parity')
 result=dict(all_passed=True,checks=checks,exact_comparisons=comparisons,historical=historical,library_sha256=hashlib.sha256(a.library.read_bytes()).hexdigest(),production_actions=[]);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

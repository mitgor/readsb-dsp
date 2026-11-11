"""Same-receiver gap reset must preserve real native admission results exactly."""
import argparse,json,time,threading
from pathlib import Path
from collections import Counter,OrderedDict
from types import SimpleNamespace
from unittest.mock import Mock
from rescue.lowlatency_stream import LowLatency
from rescue.stock_history import StockHistory
from rescue.latency_core.native_admission import NativeAdmission
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();d=json.loads((a.root/'capture/capture.private.json').read_text());epoch=d['cases'][0]['epoch'];rows=d['stock'];lib=a.root/'bin/admission.so'
with NativeAdmission(lib,epoch=epoch) as native,NativeAdmission(lib,epoch=epoch) as reference:
 native.append_stocks(rows);reference.append_stocks(rows)
 candidates=[dict(r,source='energy') for r in rows]+[r for b in d['base'] for r in b['extra']]
 before=native.evaluate(candidates,0,2**48);assert before[1]['verified']
 low=LowLatency.__new__(LowLatency);low.epoch=epoch;low.history=StockHistory()
 for r in rows:low.history.append(r)
 history=low.history;low.admission=native;low.cache=SimpleNamespace(lib=Mock(),h=1,epoch=epoch);low.emit=Mock();low.accounting=Mock();low.windows=OrderedDict();low.energy_pending={};low.expired_before=-1;low.count=Counter()
 started=time.process_time()
 for _ in range(1000):low.reset(epoch)
 cpu=time.process_time()-started
 assert low.history is history and len(low.history)==len(rows)
 assert native.evaluate(candidates,0,2**48)==before==reference.evaluate(candidates,0,2**48)
 assert low.count['same_epoch_stock_rebuilds_avoided']==1000
 result=dict(all_passed=True,same_epoch_resets=1000,stock_frames=len(rows),native_admission_output_audit_and_decision_parity=True,cpu_s=cpu,production_actions=[])
 (a.root/'results/reset-parity.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

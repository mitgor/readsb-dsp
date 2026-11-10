"""Exact candidate-specific view of the existing immutable stock indexes."""
import os
from rescue.shadow import evaluate
from rescue.stock_history import StockSnapshot

def evaluate_subset(frames,candidates,start,stop):
 if not isinstance(frames,StockSnapshot):return evaluate(frames,candidates,start,stop)
 payloads={r['message_hex'] for r in candidates};identities={p[2:8] for p in payloads}
 view=StockSnapshot((),{p:frames.payloads[p] for p in payloads if p in frames.payloads},{i:frames.identities[i] for i in identities if i in frames.identities})
 result=evaluate(view,candidates,start,stop)
 if os.environ.get('VERIFY_ADMISSION')=='1':assert result==evaluate(frames,candidates,start,stop),'Indexed view changes admission'
 return result

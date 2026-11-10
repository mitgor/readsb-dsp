"""Freeze only from validation metrics before any held-out RF replay."""
from common import *
import time
reports={k:json.loads((OUT/k/'training.json').read_text()) for k in ['raw','dsp']}
def key(k):
 r=reports[k];v=r['metrics']['validation'];return (-v['candidate_wrong_crc'],v['qualified_far180_additions'],v['additions'],-v['bit_errors'])
allowed=[k for k in reports if reports[k]['eligible_for_rf_evaluation']];assert allowed
chosen=max(allowed,key=key);p=ROOT/f'models/candidates/retrain-20261110/{chosen}/tiny-rf-v1.onnx'
write(OUT/'selected.json',dict(variant=chosen,model=str(p.relative_to(ROOT)),sha256=sha(p),frozen_unix=time.time(),criteria='Validation only: zero wrong CRC, qualified far additions, total additions, bit errors. Test and chronological RF not used.',validation={k:reports[k]['metrics']['validation'] for k in reports},reservation_sha256=sha(OUT/'rf-reservation-audit.json'),live_changes=False))
print(chosen)

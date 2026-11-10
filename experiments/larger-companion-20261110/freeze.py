from common import *
reports={k:json.loads((OUT/k/'training.json').read_text()) for k in ('raw','dsp')}
def key(d):
 v=d['metrics']['validation'];return (-v['candidate_wrong_crc'],v['qualified_far180_additions'],v['additions'],-v['bit_errors'])
choice=max(reports,key=lambda k:key(reports[k]));d=reports[choice]
assert d['eligible_for_rf_evaluation']
model=ROOT/f'models/candidates/larger-companion-20261110/{choice}/tiny-rf-v1.onnx'
assert not (OUT/'selected.json').exists()
write(OUT/'selected.json',dict(model=str(model.relative_to(ROOT)),sha256=sha(model),variant=choice,validation={k:v['metrics']['validation'] for k,v in reports.items()},selection='Validation only; same predeclared wrong-CRC/far/additions/bit-error ordering. RF not yet replayed.',frozen_unix=__import__('time').time()))
print(choice,sha(model))

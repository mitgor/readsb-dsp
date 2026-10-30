"""Exercise original deployed restore function against a fake routing controller."""
import ast,json,tempfile,time,unittest,os
from pathlib import Path
from unittest.mock import Mock
ORIGINAL=Path(os.environ.get('ADSB_ORIGINAL_TRIAL','missing-reference-trial.py'))
@unittest.skipUnless(ORIGINAL.is_file(),'Set ADSB_ORIGINAL_TRIAL to the preserved original monitor')
class Tests(unittest.TestCase):
 def restore(self,temporary=False,manual='dsp'):
  tree=ast.parse(ORIGINAL.read_text());node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='restore');route=Mock();save=Mock();runner=Mock()
  with tempfile.TemporaryDirectory() as d:
   state=Path(d)/'state.json';state.write_text(json.dumps(dict(original_host='stock' if temporary else 'combined',original_intent='dsp',guard_timer_active=not temporary)))
   ctl=dict(intent=lambda:manual,DSP='combined',STOCK='stock',route=route,mark=Mock(),publish=Mock(),health=lambda:True,host=lambda _: 'stock' if temporary else manual,CONFIG=Path(d)/'cfg');ctl['CONFIG'].write_text('dummy')
   scope=dict(STATE=state,json=json,time=time,locked=lambda:Mock(),ctl=ctl,subprocess=Mock(run=runner),D=Path(d),R=Path(d),save=save,active=lambda u:False)
   exec(compile(ast.Module(body=[node],type_ignores=[]),'original-restore','exec'),scope);scope['restore']('test');return route,runner
 def test_handover_stock_route_does_not_reenable_guard(self):
  route,runner=self.restore(True);route.assert_called_once_with('stock');runner.assert_not_called()
 def test_original_restore_still_returns_combined_and_guard(self):
  route,runner=self.restore();route.assert_called_once_with('combined');runner.assert_called_once()
 def test_restore_respects_human_manual_stock_intent(self):
  route,_=self.restore(False,'stock');route.assert_called_once_with('stock')
if __name__=='__main__':unittest.main()

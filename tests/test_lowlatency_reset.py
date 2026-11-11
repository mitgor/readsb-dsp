"""An IQ discontinuity must not replay receiver stock into already-valid indexes."""
import unittest
from types import SimpleNamespace
from collections import Counter,OrderedDict
from unittest.mock import Mock,patch
import ast
from pathlib import Path
from types import MethodType
module=ast.parse((Path(__file__).resolve().parents[1]/'src/rescue/lowlatency_stream.py').read_text())
reset_method=next(n for n in ast.walk(module) if isinstance(n,ast.FunctionDef) and n.name=='reset')
from rescue.stock_history import StockHistory

class ResetTests(unittest.TestCase):
 def test_repeated_same_receiver_gaps_keep_stock_and_admission(self):
  low=SimpleNamespace();low.epoch=4;low.history=StockHistory()
  for i in range(10000):low.history.append(dict(message_hex='8d40621d58c382d690c8ac2863a7',ticks=i*12000))
  history=low.history;low.admission=Mock();low.cache=SimpleNamespace(lib=Mock(),h=1,epoch=4)
  low.emit=Mock();low.accounting=Mock();low.windows=OrderedDict();low.energy_pending={};low.expired_before=10;low.count=Counter()
  scope=dict(StockHistory=StockHistory,Bridge=Mock(),SharedEnergyFeed=Mock(),ColdStartRetry=Mock())
  exec(compile(ast.Module(body=[reset_method],type_ignores=[]),'actual-lowlatency-reset','exec'),scope)
  low.reset=MethodType(scope['reset'],low)
  if True:
   for _ in range(100):low.reset(4)
   self.assertIs(low.history,history);self.assertEqual(len(low.history),10000)
   low.admission.reset.assert_not_called();low.admission.append_stocks.assert_not_called();low.cache.lib.ec_reset.assert_not_called()
   self.assertEqual(low.count['same_epoch_stock_rebuilds_avoided'],100)
   low.reset(5)
   self.assertEqual(len(low.history),0);low.admission.reset.assert_called_once_with(5);low.cache.lib.ec_reset.assert_called_once_with(1,5)

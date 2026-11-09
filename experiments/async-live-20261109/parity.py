"""Replay recorded native timing/stock through deployable relay glue, no inference."""
import json,hashlib,tempfile,argparse
from pathlib import Path
from unittest.mock import patch
from rescue.async_live_feed import Relay
from rescue.feed import beast,CORRECTION
from rescue.wire import BeastParser
p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--timing',type=Path,required=True);a=p.parse_args()
d=json.loads((a.data/'capture-v3/capture.private.json').read_text());rows=json.loads(a.native.read_text())['emitted'];c=d['cases'][0];offset=json.loads(a.timing.read_text())['clock_offset_s']
rfwall=c['queued']+offset-1.0005;events=[(r['arrival']-rfwall,0,r) for r in d['stock']]+[(r['emitted'],1,r) for r in rows];events.sort(key=lambda r:(r[0],r[1]));expected=hashlib.sha256();actual=hashlib.sha256();count=0
with tempfile.TemporaryDirectory() as t:
 cfg=Path(t)/'methods';cfg.write_text(json.dumps(dict(energy=True,crc=True,timing=True,soft=True,matched=True,coherent=True,header=False,sic=False,neural=True,pulse=True,stream1090=True)));relay=Relay(cfg);read=Path.read_text;exists=Path.exists
 def readpath(p,*x,**kw):return json.dumps(dict(sequence_acquisition=True,sequence_enabled=True,acquisition_enabled=True)) if str(p)=='/etc/default/adsb-rescue-workers.json' else read(p,*x,**kw)
 with patch.object(Path,'read_text',readpath),patch.object(Path,'exists',lambda p:True if str(p)=='/etc/default/adsb-rescue-workers.json' else exists(p)):
  for now,kind,r in events:
   if kind==0:
    wire=beast(r['message_hex'],r['ticks']+CORRECTION);expected.update(wire);relay.stock(wire,BeastParser().feed(wire)[0],now);actual.update(relay.ready(now))
   else:
    relay.batch(dict(admission='production_guarded_v1',epoch=c['epoch'],producer=r['source'],created_unix=now,alignment=dict(verified=True,matches=20,median_abs_error_us=0),extra=[r]),now,now);count+=len(BeastParser().feed(relay.ready(now)))
assert expected.digest()==actual.digest();assert count==len(rows),(count,len(rows),dict(relay.count));assert relay.count['duplicates_rejected']==0
print(json.dumps(dict(extras_expected=len(rows),extras_emitted=count,lost=0,duplicates=0,stock_byte_hash_match=True)))

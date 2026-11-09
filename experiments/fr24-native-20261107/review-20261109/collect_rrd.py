#!/usr/bin/env python3
import subprocess,json,hashlib,os
from pathlib import Path
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/incidents/fr24-drop-20261027/native-fr24-20261107/review-20261109')
code=r'''
import json,subprocess,pathlib,time
out={'collected_unix':time.time(),'rrd':{},'errors':{}}
for n in ['local_accepted','positions']:
 p='/run/collectd/localhost/dump1090-localhost/dump1090_messages-'+n+'.rrd'
 try:out['rrd'][n]=subprocess.check_output(['rrdtool','fetch',p,'AVERAGE','--start','1793836800','--end','1794225600','--resolution','300'],text=True)
 except Exception as e:out['errors'][n]=str(e)
print(json.dumps(out))
'''
b=subprocess.check_output(['ssh','adsb-rpi','python3','-'],input=code.encode(),timeout=30)
p=D/'rrd-history.json';assert not p.exists();p.write_bytes(b)
with p.open('rb') as f:os.fsync(f.fileno())
print('RRD saved',len(b),hashlib.sha256(b).hexdigest())

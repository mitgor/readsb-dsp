#!/usr/bin/env python3
"""Publish only explicit redacted artifacts to established report directory."""
import hashlib,json,subprocess,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parents[3];V=R/'validation/fr24-native-20261107'
files=['report.html','review-report.md','review-summary.json','cloud-hourly.json','hourly-comparison.json','hourly-comparison.csv']
manifest={}
for name in files:
 b=(V/name).read_bytes();sha=hashlib.sha256(b).hexdigest()
 # Reject accidentally embedded private key/config data; load key locally without printing it.
 private=Path('/Users/mit/Documents/!project/adsb-neural-rescue/incidents/fr24-drop-20261027/native-fr24-20261107/review-20261109/files/live.private.json')
 import re
 cfg=json.loads(private.read_text())['fr24_config'];key=re.search(r'^fr24key\s*=\s*"?([^"\n]+)',cfg,re.M).group(1).encode()
 assert key not in b and b'fr24key=' not in b and b'SHARING KEY' not in b
 path='/usr/share/adsb-rescue/fr24-native-20261107/'+name
 subprocess.run(['ssh','adsb-rpi','sudo','tee',path],input=b,stdout=subprocess.DEVNULL,check=True)
 remote=subprocess.check_output(['ssh','adsb-rpi','sha256sum',path],text=True).split()[0];assert remote==sha
 http=urllib.request.urlopen('http://192.168.2.195/neural-rescue/fr24-native-20261107/'+name,timeout=15).read();assert hashlib.sha256(http).hexdigest()==sha
 manifest[name]=dict(bytes=len(b),sha256=sha,http_verified=True)
(V/'review-publication.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))

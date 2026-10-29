"""Capture-only context. Never supplies decoder labels, addresses or positions."""
import json,math,threading,time,urllib.request,urllib.error
from .telemetry import distance_nm
SOURCE='https://opendata.adsb.fi'
ATTRIBUTION='Aircraft context: adsb.fi — https://adsb.fi (personal, non-commercial use)'
POLICY=dict(local_holdover_seconds=60,external_poll_seconds=30,external_max_age_seconds=30,
            external_radius_nm=250,burst_seconds=2,burst_interval_seconds=60)

def number(v):
 if type(v) not in (int,float) or not math.isfinite(v):raise ValueError('Non-finite numeric field')
 return v

def external_tracks(data,origin,now,threshold):
 stamp=number(data['now']);stamp=stamp/1000 if stamp>1e11 else stamp
 if not -5<=now-stamp<=POLICY['external_max_age_seconds']:raise ValueError('Stale external response')
 rows=data.get('ac',data.get('aircraft'))
 if not isinstance(rows,list) or len(rows)>10000:raise ValueError('Invalid aircraft list')
 out=[]
 for row in rows:
  try:
   addr=row['hex'];lat=number(row['lat']);lon=number(row['lon']);age=number(row['seen_pos']);seen=number(row['seen'])
   if not isinstance(addr,str) or len(addr)!=6 or any(c not in '0123456789abcdef' for c in addr):continue
   if not -90<=lat<=90 or not -180<=lon<=180 or not 0<=age<=30 or not 0<=seen<=30:continue
   observed=stamp-age
   if not -5<=now-observed<=30:continue
   # Direct ADS-B only; MLAT/TIS-B and unknown sources are not RF evidence.
   if row.get('type')!='adsb_icao' or row.get('mlat') or row.get('tisb'):continue
   alt=number(row['alt_baro']);d=distance_nm(lat,lon,origin)
   if not threshold<d<=250 or alt<10000:continue
   out.append(dict(icao=addr,lat=lat,lon=lon,distance_nm=d,alt_baro_ft=alt,position_unix=observed,
                   source=SOURCE,training_eligible=False,reference_only=True))
  except (KeyError,ValueError,TypeError):continue
 return sorted(out,key=lambda r:(r['distance_nm'],r['icao']))[:64]

class ExternalPoller:
 def __init__(self,origin,threshold=200):
  self.origin=origin;self.threshold=threshold;self.stop=threading.Event();self.lock=threading.Lock()
  self.state=dict(source=SOURCE,attribution=ATTRIBUTION,attempts=0,successes=0,error=None,tracks=[],updated_unix=0)
  self.thread=threading.Thread(target=self.run,daemon=True,name='capture-external-context')
 def start(self):self.thread.start()
 def snapshot(self):
  with self.lock:return dict(self.state,tracks=list(self.state['tracks']))
 def run(self):
  delay=30
  while not self.stop.is_set():
   now=time.time()
   with self.lock:self.state['attempts']+=1
   try:
    lat,lon=self.origin;url=f'{SOURCE}/api/v3/lat/{lat}/lon/{lon}/dist/250'
    req=urllib.request.Request(url,headers={'User-Agent':'adsb-neural-rescue-research/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=5) as response:blob=response.read(2*1024**2+1)
    if len(blob)>2*1024**2:raise ValueError('Oversize external response')
    tracks=external_tracks(json.loads(blob),self.origin,time.time(),self.threshold)
    with self.lock:self.state.update(tracks=tracks,updated_unix=time.time(),error=None);self.state['successes']+=1
    delay=30
   except Exception as e:
    with self.lock:self.state.update(error=str(e)[:240],tracks=[])
    delay=min(900,max(60,delay*2))
   if self.stop.wait(delay):break

class CaptureTriggers:
 def __init__(self,threshold=200):
  self.threshold=threshold;self.local={};self.active=[];self.until=0;self.next_burst=0;self.bursts=0
 def update(self,now,local,external):
  # local entries carry the last actual reception time, never poll arrival time.
  for row in local:
   stamp=row['last_seen_unix']
   if -2<=now-stamp<=5 and row['distance_nm']>self.threshold:self.local[row['icao']]=dict(row)
   elif row['distance_nm']<=self.threshold:self.local.pop(row['icao'],None)
  self.local={k:r for k,r in self.local.items() if -2<=now-r['last_seen_unix']<=60}
  fresh=[dict(r,reason='local_current') for r in self.local.values() if now-r['last_seen_unix']<=5]
  held=[dict(r,reason='local_holdover',reference_only=True) for r in self.local.values() if 5<now-r['last_seen_unix']<=60]
  missing=[dict(r,reason='external_local_missing') for r in external if 0<=now-r['position_unix']<=30 and not any(x['icao']==r['icao'] for x in fresh)]
  if fresh:
   self.active=fresh[:16];self.until=now+1.5
  elif now>=self.until:
   self.active=[]
   if now>=self.next_burst and (held or missing):
    self.active=(held+missing)[:16];self.until=now+2;self.next_burst=now+60;self.bursts+=1
  return self.active if now<self.until else []
 def report(self,now):return dict(policy=POLICY,active=self.active if now<self.until else [],burst_count=self.bursts,next_burst_unix=self.next_burst)

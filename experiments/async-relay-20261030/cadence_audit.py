"""Finite, read-only FR24 cadence audit. Own RAM buffer; disk saves12h/final.
Retains numeric event fields only, never sharing keys, full messages or RF data.
"""
import collections,datetime,gzip,json,re,signal,subprocess,time,threading
from pathlib import Path
D=Path('/var/lib/adsb-fr24-stock-trial-20261030');R=Path('/run/adsb-fr24-stock-trial-20261030')
def parse(message,unix):
 base=dict(unix=unix)
 m=re.search(r'\[feed\]\[i\]sent (\d+),(\d+) AC',message)
 if m:return dict(base,kind='send',literal_first=int(m[1]),literal_second=int(m[2]))
 m=re.search(r'filtering out (\d+) overlapping AC',message)
 if m:return dict(base,kind='overlap',aircraft=int(m[1]))
 m=re.search(r'send_interval:\s*([^,]+),\s*max age:\s*(\d+)s.*mode:\s*(\d+),\s*filtering:\s*(\w+)',message)
 if m:return dict(base,kind='sender_config',send_interval=m[1][:32],max_age_s=int(m[2]),mode=int(m[3]),filtering=m[4]=='true')
 if 'Time synchronized correctly' in message:return dict(base,kind='time_sync_success')
 return None

def main():
 plan=json.loads((D/'extension.json').read_text());end=plan['new_restore_unix'];start=plan['measurement_start_unix'];out=D/'cadence-audit-v2';out.mkdir(mode=0o700,exist_ok=False)
 wake=threading.Event();rows=[];cursor=None;last_save=time.monotonic();counts=collections.Counter();latest_config=None;stop=False;last_error=None
 def stopped(*_):
  nonlocal stop
  stop=True;wake.set()
 signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
 def flush():
  nonlocal rows,last_save
  if rows:
   target=out/('events-'+str(time.time_ns())+'.jsonl.gz');tmp=target.with_suffix('.tmp')
   with gzip.open(tmp,'wt') as f:
    for row in rows:f.write(json.dumps(row,separators=(',',':'))+'\n')
   tmp.replace(target);rows=[]
  last_save=time.monotonic()
 try:
  while not stop and time.time()<end:
   cmd=['journalctl','-u','fr24feed','--no-pager','-o','json']
   cmd += ['--after-cursor='+cursor] if cursor else ['--since='+datetime.datetime.fromtimestamp(start,datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')]
   query=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
   if query.returncode:
    last_error='journal_query_failed_'+str(query.returncode);counts['query_errors']+=1
   else:
    for line in query.stdout.splitlines():
     d=json.loads(line);cursor=d['__CURSOR'];t=int(d['__REALTIME_TIMESTAMP'])/1e6
     if not start<=t<end:continue
     event=parse(d.get('MESSAGE',''),t)
     if event:
      rows.append(event);counts[event['kind']]+=1
      if event['kind']=='sender_config':latest_config=event
    last_error=None
   if time.monotonic()-last_save>=43200 or len(rows)>50000:flush()
   status=dict(updated_unix=time.time(),counts=dict(counts),buffer_records=len(rows),latest_sender_config=latest_config,error=last_error,planned_end_unix=end,scope='Numeric audit of send/config/overlap/time-sync logs; no raw message/RF/model/route changes;12h disk saves.')
   tmp=R/'cadence-status.tmp';tmp.write_text(json.dumps(status,indent=2));tmp.replace(R/'cadence-status.json')
   wake.wait(min(60,max(0,end-time.time())))
 finally:
  flush();(out/'closed.json').write_text(json.dumps(dict(closed_unix=time.time(),counts=dict(counts),error=last_error,completed=time.time()>=end),indent=2))
if __name__=='__main__':main()

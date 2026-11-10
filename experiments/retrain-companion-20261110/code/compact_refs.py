from common import *
import bisect,collections,tarfile
P=WORK/'prepared';cases=json.loads((P/'cases.json').read_text());report=[]
for file in sorted({c['reference_file'] for c in cases}):
 path=P/file;d=json.loads(path.read_text());cc=sorted([c for c in cases if c['reference_file']==file],key=lambda c:c['sample_start']);lo=[c['sample_start']*5 for c in cc];hi=[(c['sample_start']+c['sample_count'])*5 for c in cc]
 def inside(t):
  i=bisect.bisect_right(lo,t+1440)-1;return i>=0 and t<=hi[i]+1440
 stock=sorted(d['stock'],key=lambda r:r['ticks']);times=[r['ticks'] for r in stock];chosen={(r['ticks'],r['message_hex']):r for r in stock if inside(r['ticks'])}
 for start in lo:
  end=bisect.bisect_right(times,start);begin=bisect.bisect_left(times,start-360000000);addresses=set()
  for r in reversed(stock[begin:end]):
   addr=r['message_hex'][2:8]
   if addr not in addresses:chosen[r['ticks'],r['message_hex']]=r;addresses.add(addr)
 actual=[r for r in d['actual'] if inside(r['ticks'])];annotations=[];archive=WORK/'rf-input/adsb-far-capture'/cc[0]['archive']
 with tarfile.open(archive) as t:
  for line in t.extractfile('ledger.jsonl'):
   r=json.loads(line)
   if r['record']!='dsp_annotation':continue
   x=r['annotation'];p=x.get('message_hex');tick=x.get('ticks')
   if p and tick is not None and inside(tick) and x.get('source') in ['energy','timing','soft','matched','coherent','neural','stream1090','pulse','sequence','acquisition']:annotations.append({'ticks':int(tick),'message_hex':p,'source':x['source']})
 result={'stock':sorted(chosen.values(),key=lambda r:r['ticks']),'actual':actual,'annotations':annotations};write(P/(path.stem+'-compact.json'),result);report.append({'file':file,'original_sha256':sha(path),'stock_before':len(stock),'stock_retained':len(chosen),'actual_retained':len(actual),'annotations_retained':len(annotations),'rule':'All RF frame/duplicate/conflict neighborhoods retained, plus latest causal stock packet per address within30s before each clip. Original reference preserved.'})
write(OUT/'compact-reference-audit.json',report);print(report)

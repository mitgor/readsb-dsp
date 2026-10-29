"""Structural and RF-to-journal coverage checks for capture v2 archives."""
import collections,json

def verify_ledger(tar):
 begins={};ends={};offsets=collections.Counter();last_sequence=-1;chunks=collections.Counter()
 for line in tar.extractfile('ledger.jsonl'):
  r=json.loads(line);kind=r['record']
  if kind=='rf_burst_begin':
   if r['burst_id'] in begins:raise ValueError('Duplicate burst ID')
   begins[r['burst_id']]=r
  elif kind=='rf_burst_end':
   if r['burst_id'] in ends:raise ValueError('Duplicate burst end')
   ends[r['burst_id']]=r
  elif kind in ('stream_chunk','dsp_annotation'):
   if r['sequence']<=last_sequence:raise ValueError('Journal sequence is not increasing')
   last_sequence=r['sequence'];chunks[r['stream']]+=1
   if 'file' in r:
    if r['file'] not in ('stock-full.beast','unified.beast') or r['byte_offset']!=offsets[r['file']] or r['bytes']<0:raise ValueError('Invalid stream byte range')
    offsets[r['file']]+=r['bytes']
  else:raise ValueError('Unknown journal record')
 for name in ('stock-full.beast','unified.beast'):
  if offsets[name]!=tar.getmember(name).size:raise ValueError('Unindexed stream bytes')
 referenced=set();rf_bytes=0
 def check(ident,epoch,sample,count,name,offset):
  nonlocal rf_bytes
  if ident not in begins or ident not in ends:raise ValueError('RF has no closed packet ledger')
  b,e=begins[ident],ends[ident]
  if epoch!=b['epoch'] or epoch!=e['epoch'] or name!=b['rf_file'] or sample<b['sample_start'] or sample+count>e['sample_end']:raise ValueError('RF outside burst sample range')
  if offset!=b['rf_byte_start']+(sample-b['sample_start'])*2 or offset+count*2>tar.getmember(name).size:raise ValueError('RF byte/sample clock mismatch')
  referenced.add(ident);rf_bytes+=count*2
 for line in tar.extractfile('segments.jsonl'):
  r=json.loads(line)
  if r.get('record')=='continuous_segment':check(r['burst_id'],r['epoch'],r['sample_start'],r['sample_count'],r['file'],r['byte_offset'])
 for line in tar.extractfile('packets.jsonl'):
  r=json.loads(line)
  if r.get('raw_available') and r['iq_file']=='packets.uc8':check(r['burst_id'],r['epoch'],r['sample_start'],r['iq_bytes']//2,r['iq_file'],r['iq_byte_offset'])
 missing=set(begins)-set(ends);incomplete=missing|{k for k,v in ends.items() if not v.get('streams_complete')}
 return dict(bursts=len(begins),referenced_bursts=len(referenced),rf_bytes=rf_bytes,stream_chunks=dict(chunks),stream_bytes=dict(offsets),incomplete_bursts=sorted(incomplete),synchronized_coverage_complete=not incomplete,method_annotations='best_effort; actual validated output in unified.beast')


def ledger_frames(tar):
 """Parse indexed TCP chunks, resetting at capture gaps and reconnects.

 Concatenating disjoint raw stream windows can otherwise splice a partial Beast
 frame from one window onto bytes from the next. Keep the journal authoritative.
 """
 from .wire import BeastParser
 streams={s:tar.extractfile(name) for s,name in (('stock','stock-full.beast'),('unified','unified.beast'))};parsers={s:BeastParser(preserve_wire=True) for s in streams};out={s:[] for s in streams};last=None
 for line in tar.extractfile('ledger.jsonl'):
  r=json.loads(line)
  if r['record'] not in ('stream_chunk','dsp_annotation'):continue
  if last is not None and r['sequence']!=last+1:parsers={s:BeastParser(preserve_wire=True) for s in streams}
  last=r['sequence'];stream=r['stream']
  if stream not in streams:continue
  if r.get('event'):parsers[stream]=BeastParser(preserve_wire=True)
  f=streams[stream];f.seek(r['byte_offset']);blob=f.read(r['bytes'])
  if len(blob)!=r['bytes']:raise ValueError('Truncated stream chunk')
  out[stream].extend(dict(row,epoch=r['epoch']) for row in parsers[stream].feed(blob))
 return out

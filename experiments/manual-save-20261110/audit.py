import pathlib,hashlib,json,gzip,base64,collections,os,tarfile
R=pathlib.Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/daily-20261110-manual-save';m=json.loads((O/'combined-input-manifest.json').read_text());archives=[];reserve=[];crc=collections.Counter()
for f in m['files']:
 p=pathlib.Path(f['local']);assert hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']
 if p.suffix=='.tar':
  with tarfile.open(p) as t:
   manifest=json.load(t.extractfile('manifest.json'));assert manifest['schema']=='far-capture-v3'
   for n,v in manifest['files'].items():
    h=hashlib.sha256();size=0
    with t.extractfile(n) as stream:
     while b:=stream.read(1024**2):size+=len(b);h.update(b)
    assert size==v['bytes'] and h.hexdigest()==v['sha256'],n
   segments=[json.loads(l) for l in t.extractfile('segments.jsonl')];training=[json.loads(l) for l in t.extractfile('training.jsonl')]
   for s in segments:
    if s.get('record')=='continuous_segment':reserve.append(dict(epoch=int(s['epoch']),sample_start=int(s['sample_start']),sample_count=int(s['sample_count'])))
   archives.append(dict(path=str(p),sha256=f['sha256'],all_member_hashes_verified=True,schema=manifest['schema'],offered_training=len(training),bands=dict(collections.Counter('180-200' if r['distance_nm']<200 else '200-250' if r['distance_nm']<250 else '250+' for r in training)),continuous_segments=sum(s.get('record')=='continuous_segment' for s in segments)))
 else:
  for l in gzip.open(p,'rt'):
   r=json.loads(l);crc['records']+=1;crc['record_'+r.get('record','unknown')]+=1
   if 'iq_uc8_base64' in r:
    assert hashlib.sha256(base64.b64decode(r['iq_uc8_base64'])).hexdigest()==r['iq_sha256'];crc['iq_verified']+=1
    assert r.get('training_eligible') is not True;crc['quarantined']+=1
# Reserve all newly downloaded continuous RF globally before label qualification.
P=R/'data/raw/long-validation-daily-20261110-manual-save';P.mkdir(exist_ok=True);p=P/'reserved-intervals.json';assert not p.exists()
with p.open('w') as out:json.dump(dict(schema='long-validation-v1',evaluation_only=True,captures=reserve,source_archives=[dict(path=r['path'],sha256=r['sha256']) for r in archives]),out,indent=2);out.flush();os.fsync(out.fileno())
fd=os.open(P,os.O_RDONLY);os.fsync(fd);os.close(fd)
audit=dict(archives=archives,crc=dict(crc),reserved_continuous_segments=len(reserve));(O/'new-data-audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit))

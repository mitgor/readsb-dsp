"""Capture-only, time-spread far stock labels with original RF and strict provenance.

Stock supplies labels for the same transmission, never a DSP/neural prediction.
Independent no-correction replay is still required before training eligibility.
"""
import collections,hashlib,json,math,time
RATE=2400000
RAM_LIMIT=48*1024**2
FILES=('training.uc8','training.jsonl')

def valid_df17(p):
 try:
  if len(p)!=28 or int(p[:2],16)>>3!=17:return False
  v=int(p,16)
  for bit in range(111,23,-1):
   if v&(1<<bit):v^=0x1fff409<<(bit-24)
  return v==0
 except (ValueError,TypeError):return False

def position(rec,addr,unix):
 for item in reversed(rec.positions.get(addr,())):
  if len(item)<3:continue
  stamp,distance,q=item
  if not isinstance(q,dict):continue
  available=q.get('available_unix')
  if not isinstance(available,(int,float)) or not math.isfinite(available) or available>unix:continue
  if not 0<=unix-stamp<=15 or not math.isfinite(distance) or distance<180:continue
  if not all(type(q.get(k)) in (int,float) and math.isfinite(q[k]) and q[k]>=5 for k in ('nic','nac_p')):continue
  if any(k in q.get('mlat_fields',[]) for k in ('lat','lon')) or q.get('tisb_fields'):continue
  return stamp,distance,q
 return None

class FarTraining:
 def __init__(self,rec):
  self.rec=rec;self.pending=collections.deque(maxlen=256);self.count=collections.Counter();self.hour=None;self.strata=collections.Counter();self.minutes=collections.Counter();self.aircraft=collections.Counter();self.seen=set();self.batches=0
 def used_bytes(self):return sum(self.rec.batch.lengths[n] for n in FILES)
 def offer(self,row,ticks,unix,epoch,source):
  if source!='stock' or not valid_df17(row.get('message_hex','')):return
  p=row['message_hex'];addr=p[2:8];q=position(self.rec,addr,unix)
  if q is None:self.count['position_quality_or_range_rejected']+=1;return
  stamp,distance,quality=q;bucket=int(unix//3600)
  if self.hour is not None and bucket<self.hour:self.count['old_clock_rejected']+=1;return
  if bucket!=self.hour:self.hour=bucket;self.strata.clear();self.minutes.clear();self.aircraft.clear();self.seen.clear()
  minute=int(unix//60);band='180-200' if distance<200 else ('200-250' if distance<250 else '250+')
  self.minutes=collections.Counter({k:v for k,v in self.minutes.items() if k[0]>=minute-1})
  self.aircraft=collections.Counter({k:v for k,v in self.aircraft.items() if isinstance(k,str) or k[1]>=minute-1})
  self.count['eligible_stock_seen']+=1
  if self.strata[band]>=80 or self.minutes[(minute,band)]>=2 or self.aircraft[(addr,minute)] or self.aircraft[addr]>=24:self.count['time_or_diversity_quota_skips']+=1;return
  key=(epoch,ticks,p)
  if key in self.seen:self.count['duplicate_skips']+=1;return
  if len(self.pending)>=self.pending.maxlen:self.count['pending_full']+=1;return
  # Keep >2 ms original RF; align the 5:3 resampling phase and exact Beast clock.
  center=round(ticks/5);lo=center-2400;lo-=lo%3;hi=lo+4800
  self.pending.append((time.monotonic(),dict(record='stock_training_candidate',schema='far-stock-training-v1',epoch=epoch,sample_start=lo,sample_count=4800,sample_rate=RATE,event_ticks=ticks,event_sample_in_window=(ticks-lo*5)/5,event_sample_4msps_in_window=(ticks-lo*5)/3,event_unix=unix,unix=unix+(lo-ticks/5)/RATE,target_hex=p,source='stock',label_provenance='same_transmission_stock_crc_valid',training_eligible=False,qualification_required='independent_uncorrected_RF_decode_and_reserved_RF_split_exclusions',distance_nm=distance,position_unix=stamp,position_age_s=unix-stamp,position_quality=quality,position_provenance='causal_stock_nic_nacp_ge5_no_mlat_no_tisb',range_verified=False,gain_db=self.rec.health.get('gain_db'),beast_wire_hex=row.get('wire_hex'),signal_byte=row.get('signal_byte'),rf_partition='training_candidate_never_prospective_evaluation')))
  # Reserve quotas at admission; a failed RF extraction never floods the queue.
  self.strata[band]+=1;self.minutes[(minute,band)]+=1;self.aircraft[(addr,minute)]+=1;self.aircraft[addr]+=1;self.seen.add(key);self.count['offered_'+band]+=1
 def drain(self):
  while self.pending:
   created,row=self.pending[0];lo=row['sample_start'];hi=lo+row['sample_count']
   if self.rec.expected is None or self.rec.expected<hi:
    if time.monotonic()-created<3:break
   self.pending.popleft()
   if row['epoch']!=self.rec.epoch:self.count['epoch_skip']+=1;continue
   raw=self.rec.extract(lo,hi)
   if raw is None:self.count['rf_gap_or_expired']+=1;continue
   if any(e==row['epoch'] and start<hi and end>lo for e,start,end,offset in self.rec.batch.raw_index):self.count['reserved_continuous_overlap_skips']+=1;continue
   row.update(iq_file='training.uc8',iq_byte_offset=self.rec.batch.lengths['training.uc8'],iq_bytes=len(raw),iq_sha256=hashlib.sha256(raw).hexdigest(),iq_format='unsigned_8bit_interleaved_IQ')
   metadata=(json.dumps(row,separators=(',',':'))+'\n').encode();size=len(raw)+len(metadata)
   if self.used_bytes()+size>RAM_LIMIT:self.count['training_ram_cap_skips']+=1;continue
   if not self.rec.allowance(size,training=True):self.count['shared_cap_skips']+=1;continue
   self.rec.batch.append('training.uc8',raw);self.rec.batch.append('training.jsonl',metadata);self.count['saved']+=1
 def restore(self,status):
  # Never erase the hourly limits on a collector-only restart.
  if not isinstance(status,dict):return
  hour=status.get('hour_bucket');strata=status.get('strata_used',{});aircraft=status.get('aircraft_used',{})
  if type(hour) is int and isinstance(strata,dict) and isinstance(aircraft,dict):
   self.hour=hour;self.strata=collections.Counter({k:int(v) for k,v in strata.items() if k in ('180-200','200-250','250+') and type(v) is int and 0<=v<=80});self.aircraft=collections.Counter({k:int(v) for k,v in aircraft.items() if len(k)==6 and type(v) is int and 0<=v<=24})
  for minute,band,count in status.get('minute_used',[]):
   if type(minute) is int and band in ('180-200','200-250','250+') and type(count) is int and 0<=count<=2:self.minutes[(minute,band)]=count
  for addr,minute in status.get('aircraft_minutes',[]):
   if isinstance(addr,str) and len(addr)==6 and type(minute) is int:self.aircraft[(addr,minute)]=1
 def report(self):
  return dict(enabled=True,schema='far-stock-training-v1',threshold_nm=180,ram_limit_bytes=RAM_LIMIT,ram_bytes=self.used_bytes(),hour_bucket=self.hour,strata_used=dict(self.strata),minute_used=[[minute,band,v] for (minute,band),v in self.minutes.items()],aircraft_minutes=[[k[0],k[1]] for k in self.aircraft if isinstance(k,tuple)],aircraft_used={k:v for k,v in self.aircraft.items() if isinstance(k,str)},counts=dict(self.count),pending=len(self.pending),policy='At most 80 windows/hour per distance band, 2/minute/band, one/aircraft/minute, 24/aircraft/hour; original 2ms RF, same-transmission CRC-valid stock; independent uncorrected replay required. No DSP/neural/external labels.')

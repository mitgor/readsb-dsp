"""Capture-only hourly RF quotas. No disk I/O, networking or decoder changes."""
import math

class CaptureSchedule:
 def __init__(self,continuous_bytes,enabled=True):
  self.enabled=enabled;self.hour_seconds=min(3.,continuous_bytes/4800000/12*.85);self.burst_seconds=self.hour_seconds
  self.bucket=None;self.used=0.;self.burst_used=0.;self.last_end=None;self.epoch=None;self.not_before=0.;self.skipped=0;self.bursts=0
  self.packet_bucket=None;self.packet_bytes=0;self.packet_cap=512*1024;self.packet_skipped=0
 def permit(self,epoch,start,unix,count):
  if not self.enabled:return True
  bucket=int(unix//3600)
  if self.bucket is not None and bucket<self.bucket:self.skipped+=1;return False
  if bucket!=self.bucket:self.bucket=bucket;self.used=0.;self.last_end=None;self.burst_used=0.
  duration=count/2400000
  continuing=self.epoch==epoch and self.last_end==start
  if unix<self.not_before or self.used+duration>self.hour_seconds+1e-9:self.skipped+=1;return False
  if continuing and self.burst_used+duration>self.burst_seconds+1e-9:
   self.last_end=None;self.not_before=unix+900;self.skipped+=1;return False
  if not continuing and self.last_end is not None and unix<self.not_before+900:self.skipped+=1;return False
  if not continuing and duration>self.burst_seconds:self.skipped+=1;return False
  return True
 def recorded(self,epoch,start,unix,count):
  continuing=self.epoch==epoch and self.last_end==start
  if not continuing:self.burst_used=0.;self.bursts+=1
  duration=count/2400000;self.used+=duration;self.burst_used+=duration;self.epoch=epoch;self.last_end=start+count;self.not_before=unix
 def report(self):
  return dict(enabled=self.enabled,policy='hourly_3s_rf_plus_bounded_packet_metadata',hour_seconds=self.hour_seconds,max_burst_seconds=self.burst_seconds,bucket=self.bucket,used_seconds=self.used,burst_used_seconds=self.burst_used,not_before_unix=self.not_before,skipped_chunks=self.skipped,bursts=self.bursts,packet_bucket=self.packet_bucket,packet_bytes=self.packet_bytes,packet_cap_bytes_per_hour=self.packet_cap,packet_skipped=self.packet_skipped,packet_iq_policy='references_to_scheduled_continuous_RF_only')
 def permit_packet(self,unix,size):
  if not self.enabled:return True
  bucket=int(unix//3600)
  if self.packet_bucket is not None and bucket<self.packet_bucket:self.packet_skipped+=1;return False
  if bucket!=self.packet_bucket:self.packet_bucket=bucket;self.packet_bytes=0
  if self.packet_bytes+size>self.packet_cap:self.packet_skipped+=1;return False
  return True
 def recorded_packet(self,size):self.packet_bytes+=size
 def restore(self,status):
  if not isinstance(status,dict):return
  bucket=status.get('bucket');used=status.get('used_seconds')
  if isinstance(bucket,int) and isinstance(used,(int,float)) and math.isfinite(used) and 0<=used<=self.hour_seconds+1e-6:
   self.bucket=bucket;self.used=float(used);self.last_end=None
   stamp=status.get('not_before_unix',0)
   if isinstance(stamp,(int,float)) and math.isfinite(stamp):self.not_before=stamp+900
  if isinstance(status.get('packet_bucket'),int) and isinstance(status.get('packet_bytes'),int) and 0<=status['packet_bytes']<=self.packet_cap:
   self.packet_bucket=status['packet_bucket'];self.packet_bytes=status['packet_bytes']

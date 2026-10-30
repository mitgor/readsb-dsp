//! Single-owner bounded transmission history. No sockets, inference or CRC repair.
use std::collections::{HashMap,VecDeque};
type Key=([u8;14],i64);
struct Entry {id:u64,ticks:i64,source:u8}
pub struct History {ttl:u64,tol:i64,cap:usize,epoch:Option<u64>,latest:Option<i64>,serial:u64,index:HashMap<Key,Vec<Entry>>,expiry:VecDeque<(u64,Key,u64)>,count:[u64;12]}
impl History {
 fn reset(&mut self,epoch:u64){self.index.clear();self.expiry.clear();self.epoch=Some(epoch);self.latest=None;self.count[2]+=1;}
 fn prune(&mut self,now:u64){
  while let Some(&(deadline,key,id))=self.expiry.front(){
   let capacity=self.expiry.len()>self.cap;if deadline>now&&!capacity{break;}
   self.expiry.pop_front();self.count[if capacity{1}else{0}]+=1;
   if let Some(bucket)=self.index.get_mut(&key){bucket.retain(|e|e.id!=id);if bucket.is_empty(){self.index.remove(&key);}}
  }
 }
 fn push(&mut self,source:u8,epoch:u64,ticks:i64,payload:[u8;14],now:u64,validated:bool)->bool{
  self.prune(now);let stock=source==0;
  if stock&&self.epoch!=Some(epoch){self.reset(epoch);}
  if self.epoch!=Some(epoch){self.count[3]+=1;return false;}
  if !stock&&!validated{self.count[4]+=1;return false;}
  if stock{self.latest=Some(self.latest.map_or(ticks,|v|v.max(ticks)));}
  else if self.latest.is_none()||self.latest.unwrap() as i128-ticks as i128>(self.ttl as i128*12/1000){self.count[5]+=1;return false;}
  let bin=ticks.div_euclid(self.tol);let mut found=false;let mut prior_extra=false;
  for delta in -1i64..=1 {if let Some(q)=bin.checked_add(delta){if let Some(bucket)=self.index.get(&(payload,q)){
   for e in bucket {if (e.ticks as i128-ticks as i128).abs()<=self.tol as i128{found=true;prior_extra|=e.source!=0;}}
  }}}
  if found {
   if !stock{self.count[6]+=1;return false;}
   if prior_extra{self.count[7]+=1;}
   self.count[8]+=1;
  }
  let Some(id)=self.serial.checked_add(1) else{return false;};self.serial=id;
  let key=(payload,bin);self.index.entry(key).or_default().push(Entry{id,ticks,source});self.expiry.push_back((now.saturating_add(self.ttl),key,id));self.prune(now);
  self.count[match source{0=>9,1=>10,_=>11}]+=1;true
 }
}
#[no_mangle] pub extern "C" fn ec_new(ttl:u64,tol:i64,cap:usize)->*mut History{
 if ttl==0||ttl>60_000_000_000||tol<=0||cap==0||cap>1_000_000{return std::ptr::null_mut();}
 Box::into_raw(Box::new(History{ttl,tol,cap,epoch:None,latest:None,serial:0,index:HashMap::new(),expiry:VecDeque::new(),count:[0;12]}))
}
#[no_mangle] pub unsafe extern "C" fn ec_free(p:*mut History){if !p.is_null(){drop(Box::from_raw(p));}}
#[no_mangle] pub unsafe extern "C" fn ec_reset(p:*mut History,epoch:u64){if let Some(h)=p.as_mut(){h.reset(epoch);}}
#[no_mangle] pub unsafe extern "C" fn ec_prune(p:*mut History,now:u64){if let Some(h)=p.as_mut(){h.prune(now);}}
#[no_mangle] pub unsafe extern "C" fn ec_push(p:*mut History,source:u8,epoch:u64,ticks:i64,payload:*const u8,now:u64,validated:bool)->i32{
 if source>2||payload.is_null(){return -1;}let Some(h)=p.as_mut() else{return -1;};let mut bytes=[0u8;14];bytes.copy_from_slice(std::slice::from_raw_parts(payload,14));h.push(source,epoch,ticks,bytes,now,validated) as i32
}
#[no_mangle] pub unsafe extern "C" fn ec_count(p:*const History,index:usize)->u64{p.as_ref().map_or(0,|h|h.count.get(index).copied().unwrap_or(0))}
#[no_mangle] pub unsafe extern "C" fn ec_len(p:*const History)->usize{p.as_ref().map_or(0,|h|h.expiry.len())}
#[cfg(test)] mod tests{
 use super::*;
 #[test]fn cross_method_and_repetition(){unsafe{let h=ec_new(5_000_000_000,1440,100);let p=[1;14];assert_eq!(ec_push(h,0,7,10000,p.as_ptr(),0,true),1);assert_eq!(ec_push(h,1,7,10000,p.as_ptr(),1,true),0);assert_eq!(ec_push(h,1,7,20000,p.as_ptr(),2,true),1);assert_eq!(ec_push(h,2,7,20000,p.as_ptr(),3,true),0);assert_eq!(ec_push(h,0,7,20000,p.as_ptr(),4,true),1);assert_eq!(ec_count(h,7),1);ec_free(h);}}
 #[test]fn guards_and_expiry(){unsafe{let h=ec_new(5_000_000_000,1440,2);let p=[1;14];assert_eq!(ec_push(h,1,7,1,p.as_ptr(),0,true),0);assert_eq!(ec_push(h,0,7,100_000_000,p.as_ptr(),1,true),1);assert_eq!(ec_push(h,1,8,200_000,p.as_ptr(),2,true),0);assert_eq!(ec_push(h,1,7,100_000_001,p.as_ptr(),3,false),0);assert_eq!(ec_push(h,1,7,1,p.as_ptr(),4,true),0);ec_prune(h,5_000_000_001);assert_eq!(ec_len(h),0);ec_free(h);}}
 #[test]fn capacity_and_extremes(){unsafe{let h=ec_new(5_000_000_000,1440,1);let p=[0;14];ec_push(h,0,1,i64::MAX,p.as_ptr(),0,true);ec_push(h,0,1,i64::MIN,p.as_ptr(),1,true);assert_eq!(ec_len(h),1);assert_eq!(ec_count(h,1),1);assert_eq!(ec_push(h,1,1,i64::MIN,p.as_ptr(),2,true),0);ec_free(h);}}
}

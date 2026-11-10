//! Isolated single-owner admission. Timestamps are exact QUARTER 12MHz ticks.
//! No sockets, clock, SDR or repairs; all thresholds below scaled by four.
use std::collections::{HashMap, VecDeque};
type Payload = [u8; 14];
#[repr(C)]
#[derive(Clone, Copy)]
pub struct Row { pub ticks: i64, pub payload: Payload, pub source: u8, pub format_valid: u8 }
#[repr(C)]
#[derive(Default)]
pub struct Audit { pub matches: u64, pub median_twice_ticks: i64, pub verified: u64 }
pub struct Admission {
    cap: usize, epoch: u64, latest: Option<i64>, arrival: VecDeque<Row>,
    payloads: HashMap<Payload, Vec<i64>>, identities: HashMap<u32, Vec<(i64,Payload)>>,
}
fn address(p: &Payload)->u32 { ((p[1] as u32)<<16)|((p[2] as u32)<<8)|p[3] as u32 }
fn valid(p: &Payload)->bool {
    if p[0]>>3 != 17 { return false; }
    let mut value=0u128; for &x in p {value=(value<<8)|x as u128;}
    for bit in (24..112).rev() {if value & (1u128<<bit)!=0 {value ^= 0x1fff409u128<<(bit-24);}}
    value==0
}
fn difference(a:i64,b:i64)->i128 {(a as i128-b as i128).abs()}
fn near(rows:&[i64],t:i64,tolerance:i128)->bool {
    let i=rows.partition_point(|&x|(x as i128)<t as i128-tolerance);
    i<rows.len() && rows[i] as i128<=t as i128+tolerance
}
impl Admission {
 fn reset(&mut self, epoch:u64){self.epoch=epoch;self.latest=None;self.arrival.clear();self.payloads.clear();self.identities.clear();}
 fn append(&mut self,row:Row){
    if self.arrival.len()==self.cap {
      let old=self.arrival.pop_front().unwrap();let key=address(&old.payload);
      let empty={let rows=self.payloads.get_mut(&old.payload).unwrap();let i=rows.partition_point(|&x|x<old.ticks);rows.remove(i);rows.is_empty()};
      if empty{self.payloads.remove(&old.payload);}
      let empty={let rows=self.identities.get_mut(&key).unwrap();let value=(old.ticks,old.payload);let i=rows.partition_point(|x|*x<value);rows.remove(i);rows.is_empty()};
      if empty{self.identities.remove(&key);}
    }
    let rows=self.payloads.entry(row.payload).or_default();let i=rows.partition_point(|&x|x<row.ticks);rows.insert(i,row.ticks);
    let rows=self.identities.entry(address(&row.payload)).or_default();let value=(row.ticks,row.payload);let i=rows.partition_point(|x|*x<value);rows.insert(i,value);
    self.latest=Some(self.latest.map_or(row.ticks,|v|v.max(row.ticks)));self.arrival.push_back(row);
 }
 fn evaluate(&self,input:&[Row],selected:&mut Vec<u32>,audit:&mut Audit,count:&mut [u64]){
    let mut errors=Vec::new();let mut order=Vec::new();let mut energy:HashMap<Payload,Vec<i64>>=HashMap::new();
    for (i,r) in input.iter().enumerate(){
      if r.source>=12 {continue;}order.push(i);
      if r.source==0 {
       if r.format_valid!=0 {
        if let Some(rows)=self.payloads.get(&r.payload){
         let j=rows.partition_point(|&x|x<r.ticks);let mut best=i128::MAX;
         if j>0 {best=best.min(difference(rows[j-1],r.ticks));}if j<rows.len(){best=best.min(difference(rows[j],r.ticks));}
         if best<48000 {errors.push(best as i64);}
        }
        if valid(&r.payload){energy.entry(r.payload).or_default().push(r.ticks);}
       }
      }
    }
    for times in energy.values_mut(){times.sort();}
    errors.sort();audit.matches=errors.len() as u64;
    audit.median_twice_ticks=if errors.is_empty(){-1}else{errors[(errors.len()-1)/2]+errors[errors.len()/2]};
    audit.verified=(errors.len()>=20 && audit.median_twice_ticks<=192) as u64;
    if audit.verified==0 {count[5]=order.len() as u64;return;}
    // Stable source/timestamp ordering matches Python's stable sorted().
    order.sort_by_key(|&i|(input[i].source,input[i].ticks));
    let mut accepted:HashMap<Payload,Vec<i64>>=HashMap::new();
    for i in order {
      let r=&input[i];let p=&r.payload;let t=r.ticks;
      if r.format_valid==0 || !valid(p){count[0]+=1;continue;}
      if r.source==10 && energy.get(p).map_or(false,|v|near(v,t,5760)){count[1]+=1;continue;}
      if self.payloads.get(p).map_or(false,|v|near(v,t,5760)) || accepted.get(p).map_or(false,|v|near(v,t,5760)){count[2]+=1;continue;}
      let identities=self.identities.get(&address(p));
      let prior=identities.map_or(false,|v|{let j=v.partition_point(|(s,_)|*s<=t);j>0 && v[j-1].0 as i128>=t as i128-1440000000});
      if !prior{count[3]+=1;continue;}
      let conflict=identities.map_or(false,|v|{let mut j=v.partition_point(|(s,_)|(*s as i128)<t as i128-192);let mut yes=false;while j<v.len() && v[j].0 as i128<=t as i128+192{if v[j].1!=*p {yes=true;break;}j+=1;}yes});
      if conflict{count[4]+=1;continue;}
      let rows=accepted.entry(*p).or_default();let j=rows.partition_point(|&s|s<t);rows.insert(j,t);selected.push(i as u32);count[6+r.source as usize]+=1;
    }
 }
}
#[no_mangle] pub extern "C" fn na_row_size()->usize{std::mem::size_of::<Row>()}
#[no_mangle] pub extern "C" fn na_audit_size()->usize{std::mem::size_of::<Audit>()}
#[no_mangle] pub extern "C" fn na_new(cap:usize,epoch:u64)->*mut Admission {
 if cap==0 || cap>1_000_000{return std::ptr::null_mut();}
 Box::into_raw(Box::new(Admission{cap,epoch,latest:None,arrival:VecDeque::new(),payloads:HashMap::new(),identities:HashMap::new()}))
}
#[no_mangle] pub unsafe extern "C" fn na_free(p:*mut Admission){if !p.is_null(){drop(Box::from_raw(p));}}
#[no_mangle] pub unsafe extern "C" fn na_reset(p:*mut Admission,epoch:u64)->i32{let Some(h)=p.as_mut()else{return -1};h.reset(epoch);0}
#[no_mangle] pub unsafe extern "C" fn na_append(p:*mut Admission,epoch:u64,rows:*const Row,n:usize)->i32{
 let Some(h)=p.as_mut()else{return -1};if h.epoch!=epoch{return -2;}if n>1_000_000 || (n>0 && rows.is_null()){return -1;}
 let rows=if n==0{&[]}else{std::slice::from_raw_parts(rows,n)};
 if rows.iter().any(|r|r.format_valid==0 || !valid(&r.payload)){return -3;}
 for &row in rows {h.append(row);}0
}
#[no_mangle] pub unsafe extern "C" fn na_latest(p:*const Admission,value:*mut i64)->i32{let Some(h)=p.as_ref()else{return -1};if value.is_null(){return -1;}match h.latest{None=>0,Some(v)=>{*value=v;1}}}
#[no_mangle] pub unsafe extern "C" fn na_len(p:*const Admission)->usize{p.as_ref().map_or(0,|h|h.arrival.len())}
#[no_mangle] pub unsafe extern "C" fn na_evaluate(p:*const Admission,epoch:u64,rows:*const Row,n:usize,selected:*mut u32,capacity:usize,output_count:*mut usize,audit:*mut Audit,counters:*mut u64,counters_len:usize)->i32{
 if !output_count.is_null(){*output_count=0;}
 let Some(h)=p.as_ref()else{return -1};if h.epoch!=epoch{return -2;}
 if output_count.is_null() || audit.is_null() || counters.is_null() || counters_len!=18 || n>100000 || capacity<n || (n>0 && (rows.is_null() || selected.is_null())){return -1;}
 let input=if n==0{&[]}else{std::slice::from_raw_parts(rows,n)};let count=std::slice::from_raw_parts_mut(counters,counters_len);count.fill(0);*audit=Audit::default();let mut result=Vec::with_capacity(n);h.evaluate(input,&mut result,&mut *audit,count);
 for (i,&v) in result.iter().enumerate(){*selected.add(i)=v;}*output_count=result.len();0
}

// SPDX-License-Identifier: GPL-3.0-or-later
// Offline port of pipeline_extended_neon.c scoring + bounded selector.
use std::{cmp::Ordering,ffi::c_int,slice};
#[derive(Clone,Copy,Debug)]struct Peak{score:f64,position:usize}
#[cfg(target_arch="aarch64")]
unsafe fn on_sums(p:&[f32],at:usize)->[f64;4]{
 use std::arch::aarch64::*;
 let mut sum01=vdupq_n_f64(0.0);let mut sum23=vdupq_n_f64(0.0);
 // Validate one fixed footprint; constant offsets avoid per-tap bounds checks.
 let block=&p[at..at+53];
 macro_rules! add {($k:expr)=>{{let samples=vld1q_f32(block[$k..$k+4].as_ptr());sum01=vaddq_f64(sum01,vcvt_f64_f32(vget_low_f32(samples)));sum23=vaddq_f64(sum23,vcvt_f64_f32(vget_high_f32(samples)));}};}
 add!(0);add!(1);add!(4);add!(5);add!(14);add!(15);add!(18);add!(19);add!(32);add!(33);add!(38);add!(39);add!(42);add!(43);add!(46);add!(47);add!(48);add!(49);
 let mut out=[0.0;4];vst1q_f64(out.as_mut_ptr(),sum01);vst1q_f64(out[2..].as_mut_ptr(),sum23);out
}
fn scores(p:&[f32],on:f64,off:f64,norm:f64,out:&mut[f64]){
 let mut total=0.0;let mut square=0.0;for k in 0..52{total+=p[k] as f64;square+=(p[k] as f64)*(p[k] as f64);}
 let mut i=0;
 #[cfg(target_arch="aarch64")]
 while i+3<=p.len()-52{
  let sums=unsafe{on_sums(p,i)};
  for lane in 0..4{let q=i+lane;if q!=0{let old=p[q-1] as f64;let fresh=p[q+51] as f64;total+=fresh-old;square+=fresh*fresh-old*old;}out[q]=(on*sums[lane]+off*(total-sums[lane]))/(square.max(1e-12)*norm).sqrt();}
  i+=4;
 }
 while i<=p.len()-52{
  if i!=0{let old=p[i-1] as f64;let fresh=p[i+51] as f64;total+=fresh-old;square+=fresh*fresh-old*old;}
  let mut sum=0.0;for k in [0,1,4,5,14,15,18,19,32,33,38,39,42,43,46,47,48,49]{sum+=p[i+k] as f64;}
  out[i]=(on*sum+off*(total-sum))/(square.max(1e-12)*norm).sqrt();i+=1;
 }
}
fn fast_peaks(score:&[f64])->Result<Vec<i64>,i64>{
 let n=score.len();if n<3||n>10_000_000{return Err(-1);}
 let mut peaks=Vec::new();peaks.try_reserve_exact(n).map_err(|_|-1i64)?;let mut j=1;
 while j<n-1{
  if score[j]>=0.30&&score[j]>score[j-1]{
   let mut end=j;while end+1<n&&score[end+1]==score[j]{end+=1;}
   if end<n-1&&score[end]>score[end+1]{peaks.push(Peak{score:score[j],position:(j+end)/2});}j=end;
  }j+=1;
 }
 peaks.sort_unstable_by(|x,y|if x.score!=y.score{if x.score>y.score{Ordering::Less}else{Ordering::Greater}}else{y.position.cmp(&x.position)});
 if peaks.windows(2).any(|p|p[0].score==p[1].score){return Err(-2);}
 let mut masked=Vec::new();masked.try_reserve_exact(n).map_err(|_|-1i64)?;masked.resize(n,0u8);let mut keep=0;
 for j in 0..peaks.len(){let pos=peaks[j].position;if masked[pos]!=0{continue;}for at in pos.saturating_sub(2)..=(pos+2).min(n-1){masked[at]=1;}peaks[keep]=peaks[j];keep+=1;}
 peaks.truncate(keep);peaks.sort_unstable_by_key(|p|p.position);
 let mut out=Vec::new();out.try_reserve_exact(n).map_err(|_|-1i64)?;for p in peaks{out.push(p.position as i64);}Ok(out)
}
#[no_mangle]
pub unsafe extern "C" fn rescue_extended_scores_neon(p:*const f32,n:i64,on:f64,off:f64,norm:f64,out:*mut f64)->c_int{
 if n<52||!norm.is_finite()||norm<=0.0{return -1;}
 scores(slice::from_raw_parts(p,n as usize),on,off,norm,slice::from_raw_parts_mut(out,n as usize-51));0
}
#[no_mangle]
pub unsafe extern "C" fn rescue_extended_select_neon(p:*const f32,n:i64,core:i64,on:f64,off:f64,norm:f64,budget:c_int,out_ids:*mut i64,out_score:*mut f64)->i64{
 if n<52||n>10_000_051||core<0||budget<1||budget>256||out_ids.is_null()||out_score.is_null(){return -1;}
 if !norm.is_finite()||norm<=0.0{return -1;}
 let length=n as usize-51;let mut sc=Vec::new();if sc.try_reserve_exact(length).is_err(){return -1;}sc.resize(length,0.0);
 scores(slice::from_raw_parts(p,n as usize),on,off,norm,&mut sc);
 let peaks=match fast_peaks(&sc){Ok(v)=>v,Err(code)=>return code};let ids=slice::from_raw_parts_mut(out_ids,budget as usize);let values=slice::from_raw_parts_mut(out_score,budget as usize);let mut count=0;
 for pos in peaks{
  if pos<8||pos>=core||pos+488>=n{continue;}
  let score=sc[pos as usize];let mut at=0;while at<count&&values[at]>=score{at+=1;}if at>=budget as usize{continue;}
  if count<budget as usize{count+=1;}for k in (at+1..count).rev(){ids[k]=ids[k-1];values[k]=values[k-1];}ids[at]=pos;values[at]=score;
 }
 count as i64
}
#[cfg(test)]mod tests{
 use super::*;
 #[test]fn ties_fall_back(){assert_eq!(fast_peaks(&[0.,0.5,0.,0.5,0.]).unwrap_err(),-2);}
 #[test]fn plateau_midpoint(){assert_eq!(fast_peaks(&[0.,0.,0.6,0.6,0.6,0.,0.]).unwrap(),vec![3]);}
 #[test]fn distance(){assert_eq!(fast_peaks(&[0.,0.5,0.,0.6,0.]).unwrap(),vec![3]);}
 #[test]fn invalid_count(){unsafe{assert_eq!(rescue_extended_select_neon(std::ptr::null(),51,0,0.,0.,1.,16,std::ptr::null_mut(),std::ptr::null_mut()),-1);}}
}

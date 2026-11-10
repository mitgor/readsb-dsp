// SPDX-License-Identifier: GPL-3.0-or-later
// Exact eight-tap discriminant/bank port. No CRC, header or address changes.
use std::ffi::{c_int,c_char};
#[link(name="m")]
extern "C" {fn fmax(a:f64,b:f64)->f64;fn fmin(a:f64,b:f64)->f64;}
const PRE:[usize;8]=[0,1,4,5,14,15,18,19];
#[no_mangle]
pub unsafe extern "C" fn rescue_pulse_discriminant(power:*const f32,length:i64,starts:*const i64,count:i64,weights:*const f64,bias:f64,logits:*mut f32,confidence:*mut f32)->c_int {
 if length<482||count<0||!bias.is_finite()||weights.is_null(){return -1;}
 let mut w=[0.0;8];for k in 0..8{w[k]=*weights.add(k);if !w[k].is_finite(){return -1;}}
 if count==0{return 0;}if power.is_null()||starts.is_null()||logits.is_null()||confidence.is_null(){return -1;}
 for j in 0..count as usize {
  let at=*starts.add(j);if at<0||at>length-482{return -1;}let at=at as usize;let mut scale=0.0;
  for k in 0..8{let p=*power.add(at+PRE[k]) as f64;if !p.is_finite()||p<0.0{return -1;}scale+=p;}
  scale=fmax(scale/8.0,1e-6);
  for bit in 0..112{let mut sum=0.0;let mut den=0.0;
   for k in 0..8{let p=*power.add(at+30+4*bit+k) as f64;if !p.is_finite()||p<0.0{return -1;}sum+=w[k]*p;den+=w[k].abs()*p;}
   let value=sum/scale+bias;*logits.add(j*112+bit)=value as f32;*confidence.add(j*112+bit)=fmin(1.0,value.abs()/(den/scale+bias.abs()+1e-9)) as f32;
  }
 }
 0
}
#[no_mangle]
pub unsafe extern "C" fn rescue_pulse_bank(power:*const f32,length:i64,starts:*const i64,count:i64,weights:*const f64,bias:*const f64,models:i64,logits:*mut f32,confidence:*mut f32)->c_int {
 if length<482||count<0||models<1||models>8||weights.is_null()||bias.is_null(){return -1;}
 let models=models as usize;let mut w=[0.0;64];let mut biases=[0.0;8];
 for m in 0..models{biases[m]=*bias.add(m);if !biases[m].is_finite(){return -1;}for k in 0..8{w[m*8+k]=*weights.add(m*8+k);if !w[m*8+k].is_finite(){return -1;}}}
 if count==0{return 0;}if power.is_null()||starts.is_null()||logits.is_null()||confidence.is_null(){return -1;}
 for j in 0..count as usize {
  let at=*starts.add(j);if at<0||at>length-482{return -1;}let at=at as usize;let mut scale=0.0;
  for k in 0..8{let v=*power.add(at+PRE[k]) as f64;if !v.is_finite()||v<0.0{return -1;}scale+=v;}
  scale=fmax(scale/8.0,1e-6);
  for bit in 0..112{let mut values=[0.0;8];for k in 0..8{values[k]=*power.add(at+30+4*bit+k) as f64;if !values[k].is_finite()||values[k]<0.0{return -1;}}
   for m in 0..models{let mut sum=0.0;let mut den=0.0;for k in 0..8{sum+=w[m*8+k]*values[k];den+=w[m*8+k].abs()*values[k];}
    let value=sum/scale+biases[m];let index=(j*models+m)*112+bit;*logits.add(index)=value as f32;*confidence.add(index)=fmin(1.0,value.abs()/(den/scale+biases[m].abs()+1e-9)) as f32;
   }
  }
 }
 0
}
#[no_mangle]
pub extern "C" fn rescue_pulse_backend()->*const c_char {b"rust-1.99.1/pulse-discriminant\0".as_ptr() as *const _}

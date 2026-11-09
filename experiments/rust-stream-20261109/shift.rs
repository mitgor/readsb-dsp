// SPDX-License-Identifier: GPL-3.0-or-later
// Port of stream1090 ShiftRegisters.hpp (Copyright 2025 Martin Gronemann).
// Exact wrapping recurrence; no decoding, trust or CRC policy changes.
const POLY:u32=0x1fff409;
const HANDLED:u32=(1<<0)|(1<<4)|(1<<5)|(1<<11)|(1<<16)|(1<<17)|(1<<18)|(1<<19)|(1<<20)|(1<<21);
const fn delta(bit:u32)->u32 {let mut x=1;let mut i=0;while i<bit {x<<=1;if x&0x1000000!=0{x^=POLY;}i+=1;}x}
const DELTA55:u32=delta(55);
const DELTA111:u32=delta(111);
#[no_mangle]
pub unsafe extern "C" fn stream_shift8_scalar(low:*mut u64,high:*mut u64,c56:*mut u32,c112:*mut u32,cmp:*const u32)->u64 {
 let low=&mut *(low as *mut [u64;8]);let high=&mut *(high as *mut [u64;8]);let c56=&mut *(c56 as *mut [u32;8]);let c112=&mut *(c112 as *mut [u32;8]);let cmp=&*(cmp as *const [u32;8]);
 let mut mask=0u64;
 for i in 0..8 {
  let h=high[i];let l=low[i];let shifted=0u32.wrapping_sub((h>>63) as u32);
  let mut a=(c56[i]^(DELTA55&shifted)).wrapping_shl(1)|((h>>7)&1) as u32;
  let mut b=(c112[i]^(DELTA111&shifted)).wrapping_shl(1)|((l>>15)&1) as u32;
  let nh=(h<<1)|(l>>63);let nl=(l<<1)|cmp[i] as u64;
  a^=POLY&0u32.wrapping_sub(a>>24);b^=POLY&0u32.wrapping_sub(b>>24);
  c56[i]=a;c112[i]=b;high[i]=nh;low[i]=nl;
  mask|=(((HANDLED>>(nh>>59))&1) as u64)<<i;
 }
 mask
}

#[cfg(target_arch="aarch64")]
#[no_mangle]
pub unsafe extern "C" fn stream_shift8(low:*mut u64,high:*mut u64,c56:*mut u32,c112:*mut u32,cmp:*const u32)->u64 {
 use std::arch::aarch64::*;
 let mut mask=0;
 for i in [0usize,4] {
  let h0=vld1q_u64(high.add(i));let h1=vld1q_u64(high.add(i+2));
  let l0=vld1q_u64(low.add(i));let l1=vld1q_u64(low.add(i+2));
  let shifted=vsubq_u32(vdupq_n_u32(0),vcombine_u32(vmovn_u64(vshrq_n_u64::<63>(h0)),vmovn_u64(vshrq_n_u64::<63>(h1))));
  let mut a=veorq_u32(vld1q_u32(c56.add(i)),vandq_u32(vdupq_n_u32(DELTA55),shifted));
  let mut b=veorq_u32(vld1q_u32(c112.add(i)),vandq_u32(vdupq_n_u32(DELTA111),shifted));
  let bit56=vandq_u32(vcombine_u32(vmovn_u64(vshrq_n_u64::<7>(h0)),vmovn_u64(vshrq_n_u64::<7>(h1))),vdupq_n_u32(1));
  let bit112=vandq_u32(vcombine_u32(vmovn_u64(vshrq_n_u64::<15>(l0)),vmovn_u64(vshrq_n_u64::<15>(l1))),vdupq_n_u32(1));
  a=vorrq_u32(vshlq_n_u32::<1>(a),bit56);b=vorrq_u32(vshlq_n_u32::<1>(b),bit112);
  a=veorq_u32(a,vandq_u32(vdupq_n_u32(POLY),vsubq_u32(vdupq_n_u32(0),vshrq_n_u32::<24>(a))));
  b=veorq_u32(b,vandq_u32(vdupq_n_u32(POLY),vsubq_u32(vdupq_n_u32(0),vshrq_n_u32::<24>(b))));
  let nh0=vorrq_u64(vshlq_n_u64::<1>(h0),vshrq_n_u64::<63>(l0));let nh1=vorrq_u64(vshlq_n_u64::<1>(h1),vshrq_n_u64::<63>(l1));
  let bits=vld1q_u32(cmp.add(i));
  vst1q_u64(high.add(i),nh0);vst1q_u64(high.add(i+2),nh1);
  vst1q_u64(low.add(i),vorrq_u64(vshlq_n_u64::<1>(l0),vmovl_u32(vget_low_u32(bits))));
  vst1q_u64(low.add(i+2),vorrq_u64(vshlq_n_u64::<1>(l1),vmovl_u32(vget_high_u32(bits))));
  vst1q_u32(c56.add(i),a);vst1q_u32(c112.add(i),b);
  let df=vcombine_u32(vmovn_u64(vshrq_n_u64::<59>(nh0)),vmovn_u64(vshrq_n_u64::<59>(nh1)));
  let yes=vandq_u32(vshlq_u32(vdupq_n_u32(HANDLED),vnegq_s32(vreinterpretq_s32_u32(df))),vdupq_n_u32(1));
  let shifts=[i as i32,i as i32+1,i as i32+2,i as i32+3];mask|=vaddvq_u32(vshlq_u32(yes,vld1q_s32(shifts.as_ptr()))) as u64;
 }
 mask
}
#[cfg(not(target_arch="aarch64"))]
#[no_mangle]
pub unsafe extern "C" fn stream_shift8(l:*mut u64,h:*mut u64,a:*mut u32,b:*mut u32,c:*const u32)->u64 {stream_shift8_scalar(l,h,a,b,c)}

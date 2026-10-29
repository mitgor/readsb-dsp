// SPDX-License-Identifier: GPL-3.0-or-later
// Default Rust EM backend; only method=0. Other research methods stay in C.
// Reuse the validated Rust CRC/table helpers, never call a C DSP decoder.
include!("coherent_rust.rs");
extern "C"{fn fmax(a:f64,b:f64)->f64;fn exp(a:f64)->f64;}
#[inline]
fn rotation(z:Complex,w:f64,n:i32)->Complex{
 let (s,c)=(w*n as f64).sin_cos();z.mul(Complex{re:c,im:-s})
}
fn noise(z:&[f32])->f64{
 let mut values=[0f64;112];
 for b in 0..112{let q=32+4*b;let mut e=0.0;let mut f=0.0;for t in 0..2{let x=Complex{re:z[2*(q+t)] as f64,im:z[2*(q+t)+1] as f64};let y=Complex{re:z[2*(q+2+t)] as f64,im:z[2*(q+2+t)+1] as f64};e+=x.re*x.re+x.im*x.im;f+=y.re*y.re+y.im*y.im;}values[b]=unsafe{fmin(e,f)}*0.5;}
 unsafe{fmax(quantile(&mut values,0.5),1e-8)}
}
fn seed(z:&[f32],supplied:f64)->f64{
 if supplied.is_finite(){return supplied;}
 let mut best=-1.0;let mut frequency=0.0;let tables=tables();
 for f in 0..41{let mut a=Complex::default();for j in 0..8{let q=PRE[j];a=a.add(Complex{re:z[2*q] as f64,im:z[2*q+1] as f64}.mul(tables.carriers[f][j]));}let p=a.re*a.re+a.im*a.im;if p>best{best=p;frequency=-100000.0+5000.0*f as f64;}}
 frequency
}
fn gain(z:&[f32],w:f64,prob:&[f64])->Complex{
 let mut a=Complex::default();
 for n in 0..480{
  let mut p=0.0;
  if n<32{for j in 0..8{if n==PRE[j]{p=1.0;}}}else{let b=(n-32)/4;let t=(n-32)%4;p=if t<2{prob[b]}else{1.0-prob[b]};}
  let v=rotation(Complex{re:z[2*n] as f64,im:z[2*n+1] as f64},w,n as i32-240);a.re+=p*v.re;a.im+=p*v.im;
 }
 Complex{re:a.re/232.0,im:a.im/232.0}
}
fn em(z:&[f32],initial:f64,iterations:usize,l:&mut[f64],c:&mut[f64])->f64{
 let mut p=[0f64;112];let mut w=initial*2.0*PI/RATE;let noise=noise(z);
 for b in 0..112{p[b]=if l[b]>0.0{0.95}else{0.05};}
 let mut g=gain(z,w,&p);
 for iteration in 0..iterations{
  for b in 0..112{
   let mut d=Complex::default();
   for t in 0..2{let q=32+4*b+t;let left=rotation(Complex{re:z[2*q] as f64,im:z[2*q+1] as f64},w,q as i32-240);let right=rotation(Complex{re:z[2*(q+2)] as f64,im:z[2*(q+2)+1] as f64},w,q as i32+2-240);d.re+=left.re-right.re;d.im+=left.im-right.im;}
   let mut v=2.0*g.conjugate().mul(d).re/noise;v=unsafe{fmax(-30.0,fmin(30.0,v))};p[b]=1.0/(1.0+unsafe{exp(-v)});
  }
  let mut best=-1.0;let mut bw=w;let mut bg=g;let step=(4000.0/(1usize<<iteration) as f64)*2.0*PI/RATE;
  for k in -2..=2{let cw=w+k as f64*step;let cg=gain(z,cw,&p);let score=cg.re*cg.re+cg.im*cg.im;if score>best{best=score;bw=cw;bg=cg;}}
  w=bw;g=bg;
 }
 for b in 0..112{
  let mut left=0.0;let mut right=0.0;
  for t in 0..2{let mut q=32+4*b+t;left+=g.conjugate().mul(rotation(Complex{re:z[2*q] as f64,im:z[2*q+1] as f64},w,q as i32-240)).re;q+=2;right+=g.conjugate().mul(rotation(Complex{re:z[2*q] as f64,im:z[2*q+1] as f64},w,q as i32-240)).re;}
  l[b]=left-right;c[b]=l[b].abs()/(left.abs()+right.abs()+1e-9);
 }
 w*RATE/(2.0*PI)
}
#[no_mangle]
pub unsafe extern "C" fn rescue_science(windows:*const f32,n:i64,seeds:*const f64,initial_l:*const f64,initial_c:*const f64,_hr:*const f64,_hi:*const f64,method:c_int,iterations:c_int,out_l:*mut f64,out_c:*mut f64,rows:*mut u8,flips:*mut i8,valid:*mut u8,frequency:*mut f64)->c_int{
 if n<0||n>4096||method!=0||iterations<1||iterations>4{return -1;}
 if n==0{return 0;}
 let n=n as usize;let input=slice::from_raw_parts(windows,n*992);let seeds=slice::from_raw_parts(seeds,n);let il=slice::from_raw_parts(initial_l,n*112);let ic=slice::from_raw_parts(initial_c,n*112);let l=slice::from_raw_parts_mut(out_l,n*112);let c=slice::from_raw_parts_mut(out_c,n*112);let rows=slice::from_raw_parts_mut(rows,n*14);let flips=slice::from_raw_parts_mut(flips,n*2);let valid=slice::from_raw_parts_mut(valid,n);let f=slice::from_raw_parts_mut(frequency,n);
 for k in 0..n{let z=&input[k*992+16..k*992+976];let lo=k*112;let hi=lo+112;l[lo..hi].copy_from_slice(&il[lo..hi]);c[lo..hi].copy_from_slice(&ic[lo..hi]);f[k]=em(z,seed(z,seeds[k]),iterations as usize,&mut l[lo..hi],&mut c[lo..hi]);valid[k]=decode(&l[lo..hi],&c[lo..hi],&mut rows[k*14..(k+1)*14],&mut flips[k*2..(k+1)*2],&tables().patterns);}
 0
}

#[no_mangle]
pub extern "C" fn rescue_science_backend()->*const std::ffi::c_char{b"rust-1.99.1/soft-phase-em\0".as_ptr() as *const _}

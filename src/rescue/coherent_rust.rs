// SPDX-License-Identifier: GPL-3.0-or-later
// Production bounded coherent-window port, ordinary and pair-lag variants.
// Based on experiments/rust-coherent/coherent.rs; no C decoder calls.
// Shared elementary libm operations keep the numerical comparison controlled.
use std::{cmp::Ordering, ffi::{c_int,c_void}, slice, sync::OnceLock};
const PI:f64=std::f64::consts::PI;
const RATE:f64=4_000_000.0;
const PRE:[usize;8]=[0,1,4,5,14,15,18,19];
#[derive(Clone,Copy,Default)]
struct Complex{re:f64,im:f64}
impl Complex{
 fn add(self,b:Self)->Self{Self{re:self.re+b.re,im:self.im+b.im}}
 fn mul(self,b:Self)->Self{Self{re:self.re*b.re-self.im*b.im,im:self.re*b.im+self.im*b.re}}
 fn mag(self)->f64{unsafe{hypot(self.re,self.im)}}
 fn angle(self)->f64{unsafe{atan2(self.im,self.re)}}
 fn scale(self,x:f64)->Self{Self{re:self.re*x,im:self.im*x}}
 fn conjugate(self)->Self{Self{re:self.re,im:-self.im}}
}
#[link(name="m")]
extern "C"{
 fn hypot(a:f64,b:f64)->f64;fn hypotf(a:f32,b:f32)->f32;
 fn sin(x:f64)->f64;fn cos(x:f64)->f64;fn atan2(y:f64,x:f64)->f64;
 fn fmin(x:f64,y:f64)->f64;
}
extern "C"{fn qsort(base:*mut c_void,n:usize,size:usize,cmp:unsafe extern "C" fn(*const c_void,*const c_void)->c_int);}
#[derive(Clone,Copy)]
struct Pattern{key:u32,a:i32,b:i32}
struct Tables{patterns:[Pattern;6328],carriers:[[Complex;8];41]}
static TABLES:OnceLock<Tables>=OnceLock::new();
fn crc(row:&[u8])->u32{
 let mut c=0u32;
 for b in 0..112{let top=((c>>23)&1)^(((row[b/8] as u32)>>(7-b%8))&1);c=(c<<1)&0xffffff;if top!=0{c^=0xfff409;}}
 c
}
fn tables()->&'static Tables{TABLES.get_or_init(||{
 let mut bit=[0u32;112];let mut row=[0u8;14];
 for b in 0..112{row.fill(0);row[b/8]=1<<(7-b%8);bit[b]=crc(&row);}
 let mut patterns=[Pattern{key:0,a:0,b:0};6328];let mut n=0;
 for a in 0..112{patterns[n]=Pattern{key:bit[a],a:a as i32,b:-1};n+=1;for b in a+1..112{patterns[n]=Pattern{key:bit[a]^bit[b],a:a as i32,b:b as i32};n+=1;}}
 patterns.sort_unstable_by_key(|p|p.key);
 assert!(patterns.windows(2).all(|p|p[0].key!=p[1].key));
 let mut carriers=[[Complex::default();8];41];
 for f in 0..41{for j in 0..8{let a=-2.0*PI*(-100000.0+5000.0*f as f64)*PRE[j] as f64/RATE;carriers[f][j]=Complex{re:unsafe{cos(a)},im:unsafe{sin(a)}};}}
 Tables{patterns,carriers}
})}
#[no_mangle]
pub extern "C" fn rescue_coherent_init()->c_int{let _=tables();0}
unsafe extern "C" fn compare_double(a:*const c_void,b:*const c_void)->c_int{let x=*(a as *const f64);let y=*(b as *const f64);(x>y) as c_int-(x<y) as c_int}
fn quantile(v:&mut[f64],fraction:f64)->f64{
 if v.iter().any(|x|!x.is_finite()){unsafe{qsort(v.as_mut_ptr() as *mut c_void,v.len(),8,compare_double);}let index=(v.len()-1) as f64*fraction;let lo=index as usize;let hi=index.ceil() as usize;return v[lo]+(v[hi]-v[lo])*(index-lo as f64);}
 v.sort_unstable_by(|a,b|a.partial_cmp(b).unwrap_or(Ordering::Equal));
 let index=(v.len()-1) as f64*fraction;let lo=index as usize;let hi=index.ceil() as usize;
 v[lo]+(v[hi]-v[lo])*(index-lo as f64)
}
fn fit(x:&[f64],y:&[f64],w:&[f64],used:Option<&[i32]>)->Option<(f64,f64)>{
 let mut sw=0.0;let mut sx=0.0;let mut sy=0.0;
 for k in 0..x.len(){if used.map_or(true,|u|u[k]!=0){let q=w[k]*w[k];sw+=q;sx+=q*x[k];sy+=q*y[k];}}
 if sw<=0.0{return None;}
 let mx=sx/sw;let my=sy/sw;let mut num=0.0;let mut den=0.0;
 for k in 0..x.len(){if used.map_or(true,|u|u[k]!=0){let q=w[k]*w[k];let dx=x[k]-mx;num+=q*dx*(y[k]-my);den+=q*dx*dx;}}
 if den<=1e-30{return None;}
 let slope=num/den;Some((slope,my-slope*mx))
}
fn decode(l:&[f64],c:&[f64],row:&mut[u8],flips:&mut[i8],patterns:&[Pattern])->u8{
 row.fill(0);flips.fill(-1);
 for b in 0..112{if l[b]>0.0{row[b/8]|=1<<(7-b%8);}}
 if row[0]>>3!=17{return 0;}
 let syndrome=crc(row);if syndrome==0{return 1;}
 let mut lo=0;let mut hi=6328;
 while lo<hi{let m=lo+(hi-lo)/2;if patterns[m].key<syndrome{lo=m+1;}else{hi=m;}}
 if lo==6328||patterns[lo].key!=syndrome{return 0;}
 let mut least=[-1i32;6];
 for b in 32..112{for j in 0..6{if least[j]<0||c[b]<c[least[j] as usize]{for q in (j+1..6).rev(){least[q]=least[q-1];}least[j]=b as i32;break;}}}
 let bits=[patterns[lo].a,patterns[lo].b];
 for bit in bits{if bit>=0{let mut allowed=false;for j in 0..6{if least[j]==bit&&c[bit as usize]<=0.35{allowed=true;}}if !allowed{return 0;}}}
 for i in 0..2{if bits[i]>=0{let bit=bits[i] as usize;row[bit/8]^=1<<(7-bit%8);flips[i]=bits[i] as i8;}}
 1
}
#[no_mangle]
pub unsafe extern "C" fn rescue_coherent(iq:*const f32,total:i64,starts:*const i64,n:i64,logits:*mut f64,confidence:*mut f64,tracked:*mut u8,frequency:*mut f64,inliers:*mut i32,rows:*mut u8,flips:*mut i8,valid:*mut u8)->c_int{
 if !(0..=4096).contains(&n)||total<0{return -1;}
 if n==0{return 0;}
 if iq.is_null()||starts.is_null()||logits.is_null()||confidence.is_null()||tracked.is_null()||frequency.is_null()||inliers.is_null()||rows.is_null()||flips.is_null()||valid.is_null(){return -1;}
 let n=n as usize;let starts=slice::from_raw_parts(starts,n);
 if starts.iter().any(|&at|at<0||total<480||at>total-480){return -1;}
 let input=slice::from_raw_parts(iq,2*total as usize);
 let logits=slice::from_raw_parts_mut(logits,n*112);let confidence=slice::from_raw_parts_mut(confidence,n*112);
 let tracked=slice::from_raw_parts_mut(tracked,n);let frequency=slice::from_raw_parts_mut(frequency,n);let inliers=slice::from_raw_parts_mut(inliers,n);
 let rows=slice::from_raw_parts_mut(rows,n*14);let flips=slice::from_raw_parts_mut(flips,n*2);let valid=slice::from_raw_parts_mut(valid,n);
 let tab=tables();
 for k in 0..n{
  let at=starts[k] as usize;let z=&input[2*at..2*(at+480)];let l=&mut logits[112*k..112*(k+1)];let c=&mut confidence[112*k..112*(k+1)];
  let mut power=[0f32;480];let mut positions=[0usize;112];let mut magnitude=[0f64;112];let mut sorted=[0f64;112];
  for q in 0..480{let a=hypotf(z[2*q],z[2*q+1]);power[q]=a*a;}
  for b in 0..112{let q=32+4*b;let left=power[q]+power[q+1];let right=power[q+2]+power[q+3];l[b]=(left-right) as f64;c[b]=((left-right).abs()/(left+right+1e-9f32)) as f64;positions[b]=q+if l[b]>0.0{0}else{2};}
  #[cfg(not(coarse_pair))]
  let coarse={
   let mut selected=0;let mut best=-1.0;
   for f in 0..41{let mut a=Complex::default();for j in 0..8{let q=PRE[j];a=a.add(Complex{re:z[2*q] as f64,im:z[2*q+1] as f64}.mul(tab.carriers[f][j]));}let p=a.re*a.re+a.im*a.im;if p>best{best=p;selected=f;}}
   -100000.0+selected as f64*5000.0
  };
  #[cfg(coarse_pair)]
  let coarse={
   let mut pair=Complex::default();
   for j in 0..4{let a=PRE[j];let b=PRE[j+4];let early=Complex{re:z[2*a] as f64,im:z[2*a+1] as f64};let late=Complex{re:z[2*b] as f64,im:z[2*b+1] as f64};pair=pair.add(late.mul(early.conjugate()));}
   pair.angle()*RATE/(2.0*PI*14.0)
  };
  let mut omega=2.0*PI*coarse/RATE;
  let mut rotated=[Complex::default();480];let mut oscillator=Complex{re:1.0,im:0.0};let mut step=Complex{re:cos(omega),im:-sin(omega)};
  for q in 0..480{rotated[q]=Complex{re:z[2*q] as f64,im:z[2*q+1] as f64}.mul(oscillator);oscillator=oscillator.mul(step);}
  for b in 0..112{let q=positions[b];magnitude[b]=rotated[q].add(rotated[q+1]).scale(0.5).mag();sorted[b]=magnitude[b];}
  let cutoff=quantile(&mut sorted,0.35);let mut x=[0f64;112];let mut y=[0f64;112];let mut weights=[0f64;112];let mut mw=[0f64;112];let mut good=[0usize;112];let mut count=0;let mut previous=0.0;let mut unwrapped=0.0;
  for b in 0..112{if c[b]>=0.5&&magnitude[b]>=cutoff{
   let q=positions[b];let angle=rotated[q].add(rotated[q+1]).angle();
   if count!=0{let mut delta=angle-previous;if delta>PI{delta-=2.0*PI;}else if delta< -PI{delta+=2.0*PI;}unwrapped+=delta;}else{unwrapped=angle;}
   previous=angle;x[count]=q as f64+0.5;y[count]=unwrapped;good[count]=q;weights[count]=magnitude[b];mw[count]=magnitude[b];count+=1;
  }}
  tracked[k]=0;frequency[k]=f64::NAN;inliers[k]=0;
  if count>=24{
   let cap=2.0*quantile(&mut mw[..count],0.5);for j in 0..count{weights[j]=fmin(weights[j],cap);}
   if let Some((mut slope,mut intercept))=fit(&x[..count],&y[..count],&weights[..count],None){
    let mut used=[0i32;112];let mut kept=0;
    for j in 0..count{let r=y[j]-slope*x[j]-intercept;used[j]=(atan2(sin(r),cos(r)).abs()<0.8) as i32;kept+=used[j];}
    if kept>=24{if let Some((s,i))=fit(&x[..count],&y[..count],&weights[..count],Some(&used[..count])){slope=s;intercept=i;}}
    if slope.is_finite()&&intercept.is_finite()&&(slope*RATE/(2.0*PI)).abs()<=30000.0{
     tracked[k]=1;frequency[k]=coarse+slope*RATE/(2.0*PI);inliers[k]=kept;
     omega+=slope;step=Complex{re:cos(omega),im:-sin(omega)};oscillator=Complex{re:cos(intercept),im:-sin(intercept)};
     for q in 0..480{rotated[q]=Complex{re:z[2*q] as f64,im:z[2*q+1] as f64}.mul(oscillator);oscillator=oscillator.mul(step);}
     let mut shape=[Complex::default();2];for j in 0..count{shape[0]=shape[0].add(rotated[good[j]]);shape[1]=shape[1].add(rotated[good[j]+1]);}
     for a in &mut shape{a.re/=count as f64;a.im=-(a.im/count as f64);}
     for b in 0..112{let q=32+4*b;let left=rotated[q].mul(shape[0]).add(rotated[q+1].mul(shape[1])).re;let right=rotated[q+2].mul(shape[0]).add(rotated[q+3].mul(shape[1])).re;l[b]=left-right;c[b]=l[b].abs()/(left.abs()+right.abs()+1e-9);}
    }
   }
  }
  valid[k]=decode(l,c,&mut rows[14*k..14*(k+1)],&mut flips[2*k..2*(k+1)],&tab.patterns);
 }
 0
}
#[cfg(test)]
mod tests{
 use super::*;
 #[test]fn crc_table(){assert_eq!(tables().patterns.len(),6328);assert_eq!(rescue_coherent_init(),0);}
 #[test]fn known_crc(){let row=[0x8d,0x40,0x62,0x1d,0x58,0xc3,0x82,0xd6,0x90,0xc8,0xac,0x28,0x63,0xa7];assert_eq!(crc(&row),0);}
 #[test]fn bad_bounds(){unsafe{assert_eq!(rescue_coherent(std::ptr::null(),0,std::ptr::null(),-1,std::ptr::null_mut(),std::ptr::null_mut(),std::ptr::null_mut(),std::ptr::null_mut(),std::ptr::null_mut(),std::ptr::null_mut(),std::ptr::null_mut(),std::ptr::null_mut()),-1);}}
}

// Stable diagnostic marker; not used in the decode hot loop.
#[no_mangle]
pub extern "C" fn rescue_coherent_backend()->*const std::ffi::c_char{
 if cfg!(coarse_pair){b"rust-1.99.1/std-sort/pair\0".as_ptr() as *const _}
 else{b"rust-1.99.1/std-sort/ordinary\0".as_ptr() as *const _}
}

// SPDX-License-Identifier: GPL-3.0-or-later
// Exact optimized-v3 pulse-sequence port. Existing Rust CRC/libm helpers reused.
include!("../../src/rescue/science_em_rust.rs");
fn pulse(n:i32,bit:i32,state:usize,current:usize)->f64 {
 if n<0||n>=480{return 0.0;}if n<32{return if PRE.contains(&(n as usize)){1.0}else{0.0};}
 let b=(n-32)/4;let t=(n-32)%4;let v=if b==bit{current}else if b==bit-1{state&1}else if b==bit-2{(state>>1)&1}else{0};if t<2{v as f64}else{(1-v) as f64}
}
#[no_mangle]
pub unsafe extern "C" fn rescue_sequence_prepare(hr:*const f64,hi:*const f64,templates:*mut f64,pre:*mut f64)->c_int{
 if hr.is_null()||hi.is_null()||templates.is_null()||pre.is_null(){return -1;}
 let hr=slice::from_raw_parts(hr,9);let hi=slice::from_raw_parts(hi,9);if hr.iter().chain(hi).any(|x|!x.is_finite()){return -1;}
 let h:Vec<Complex>=(0..9).map(|k|Complex{re:hr[k],im:hi[k]}).collect();let templates=slice::from_raw_parts_mut(templates,114*64);let pre=slice::from_raw_parts_mut(pre,48);
 for b in 0..114{for s in 0..4{for v in 0..2{for t in 0..4{
  let n=32+4*b+t;let mut p=Complex::default();for k in 0..9{p=p.add(h[k].scale(pulse(n as i32-k as i32,b as i32,s,v)));}
  let q=2*(((b*4+s)*2+v)*4+t);templates[q]=p.re;templates[q+1]=p.im;
 }}}}
 for n in 4..28{let mut p=Complex::default();for k in 0..9{let j=n as i32-k as i32;if j>=0&&j<32{for t in 0..8{if j==PRE[t] as i32{p=p.add(h[k]);}}}}pre[2*(n-4)]=p.re;pre[2*(n-4)+1]=p.im;}
 0
}
fn prepared(window:&[f32],freq:f64,templates:&[f64],pre:&[f64],repeat:bool,l:&mut[f64],c:&mut[f64]){
 let w=freq*2.0*PI/RATE;let mut g=Complex::default();let mut den=0.0;
 for n in 4..28{let p=Complex{re:pre[2*(n-4)],im:pre[2*(n-4)+1]};let q=8+n-4;let y=rotation(Complex{re:window[2*q] as f64,im:window[2*q+1] as f64},w,n as i32-4-240);g=g.add(p.conjugate().mul(y));den+=p.re*p.re+p.im*p.im;}
 let den=unsafe{fmax(den,1e-12)};g.re/=den;g.im/=den;
 let mut scaled=[[[[Complex::default();4];2];4];5];let blocks=[0usize,1,2,112,113];
 if repeat{for k in 0..5{for s in 0..4{for v in 0..2{for t in 0..4{let q=2*(((blocks[k]*4+s)*2+v)*4+t);scaled[k][s][v][t]=g.mul(Complex{re:templates[q],im:templates[q+1]});}}}}}
 let mut cost=[[[0.0f64;2];4];114];let mut a=[[0.0f64;4];115];let mut back=[[0.0f64;4];115];let mut trace=[[0usize;4];114];
 for s in 0..4{a[0][s]=if s==0{0.0}else{1e100};back[114][s]=0.0;}
 for b in 0..114{
  let mut obs=[Complex::default();4];for t in 0..4{let n=32+4*b+t;let q=8+n-4;obs[t]=rotation(Complex{re:window[2*q] as f64,im:window[2*q+1] as f64},w,n as i32-4-240);}
  a[b+1]=[1e100;4];
  for s in 0..4{for v in 0..2{
   let mut e=0.0;for t in 0..4{let p=if repeat{let k=if b<2{b}else if b<112{2}else{b-109};scaled[k][s][v][t]}else{let q=2*(((b*4+s)*2+v)*4+t);g.mul(Complex{re:templates[q],im:templates[q+1]})};let dr=obs[t].re-p.re;let di=obs[t].im-p.im;e+=dr*dr+di*di;}
   if b>=112&&v!=0{e=1e100;}cost[b][s][v]=e;let next=((s&1)<<1)|v;if a[b][s]+e<a[b+1][next]{a[b+1][next]=a[b][s]+e;trace[b][next]=s;}
  }}
 }
 for b in (0..114).rev(){for s in 0..4{back[b][s]=unsafe{fmin(cost[b][s][0]+back[b+1][(s&1)<<1],cost[b][s][1]+back[b+1][((s&1)<<1)|1])};}}
 let mut state=0;for s in 1..4{if a[114][s]<a[114][state]{state=s;}}
 let mut bits=[0usize;114];for b in (0..114).rev(){bits[b]=state&1;state=trace[b][state];}
 let noise=noise(&window[16..]);
 for b in 0..112{
  let mut best=[1e100;2];for s in 0..4{for v in 0..2{let next=((s&1)<<1)|v;let x=a[b][s]+cost[b][s][v]+back[b+1][next];if x<best[v]{best[v]=x;}}}
  let strength=(best[0]-best[1]).abs();l[b]=(if bits[b]!=0{1.0}else{-1.0})*unsafe{fmax(strength,1e-20)};c[b]=1.0-unsafe{exp(-strength/fmax(4.0*noise,1e-12))};
 }
}
#[no_mangle]
pub unsafe extern "C" fn rescue_sequence_batch(iq:*const f32,length:i64,starts:*const i64,count:i64,seeds:*const f64,templates:*const f64,pre:*const f64,l:*mut f64,c:*mut f64,rows:*mut u8,flips:*mut i8,valid:*mut u8)->c_int{
 if length<496||count<0||count>4096{return -1;}if count==0{return 0;}
 if iq.is_null()||starts.is_null()||seeds.is_null()||templates.is_null()||pre.is_null()||l.is_null()||c.is_null()||rows.is_null()||flips.is_null()||valid.is_null(){return -1;}
 let count=count as usize;let starts=slice::from_raw_parts(starts,count);if starts.iter().any(|&s|s<8||s>length-488){return -1;}
 let input=slice::from_raw_parts(iq,2*length as usize);let seeds=slice::from_raw_parts(seeds,count);let templates=slice::from_raw_parts(templates,114*64);let pre=slice::from_raw_parts(pre,48);
 let l=slice::from_raw_parts_mut(l,count*112);let c=slice::from_raw_parts_mut(c,count*112);let rows=slice::from_raw_parts_mut(rows,count*14);let flips=slice::from_raw_parts_mut(flips,count*2);let valid=slice::from_raw_parts_mut(valid,count);
 let repeat=(3..112).all(|b|templates[64*b..64*(b+1)].iter().zip(&templates[128..192]).all(|(a,b)|a.to_bits()==b.to_bits()));
 for j in 0..count{let at=2*(starts[j] as usize-8);let window=&input[at..at+992];let frequency=seed(&window[16..],seeds[j]);prepared(window,frequency,templates,pre,repeat,&mut l[j*112..(j+1)*112],&mut c[j*112..(j+1)*112]);valid[j]=decode(&l[j*112..(j+1)*112],&c[j*112..(j+1)*112],&mut rows[j*14..(j+1)*14],&mut flips[j*2..(j+1)*2],&tables().patterns);}
 0
}
#[no_mangle]
pub extern "C" fn rescue_sequence_backend()->*const std::ffi::c_char{b"rust-1.99.1/pulse-sequence-v3\0".as_ptr() as *const _}

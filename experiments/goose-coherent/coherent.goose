// Direct bounded port of src/rescue/coherent_kernel.c (ordinary 41-bin build).
// No C decoder calls: externs below are libm primitives only.
import math;
import std;
extern fn hypot(x: f64, y: f64) -> f64;
extern "hypotf" fn hypot32(x: f32, y: f32) -> f32;
extern "fabs" fn abs64(x: f64) -> f64;
extern "fabsf" fn abs32(x: f32) -> f32;
extern "fmin" fn min64(x: f64, y: f64) -> f64;
struct Complex { re: f64, im: f64 }
fn mul(a: Complex, b: Complex) -> Complex { Complex { a.re*b.re-a.im*b.im, a.re*b.im+a.im*b.re } }
fn add(a: Complex, b: Complex) -> Complex { Complex { a.re+b.re,a.im+b.im } }
fn magnitude(a: Complex) -> f64 { hypot(a.re,a.im) }
struct Pattern { key: u32, a: i32, b: i32 }
var patterns: Pattern[6328] = [Pattern { 0,0,0 };6328];
var carriers: Complex[328] = [Complex {0.0,0.0};328];
let preamble: i64[8] = [0,1,4,5,14,15,18,19];
fn crc(row: const u8[:]) -> u32 {
 var c: u32=0;
 for b in 112 {
  let top=((c>>23)&1)^(((row[b/8] as u32)>>(7-b%8))&1);
  c=(c<<1)&0xffffff;
  if top!=0 { c ^= 0xfff409; }
 }
 c
}
fn main() {
 var bit: u32[112]=[0;112];var row:u8[14]=[0;14];var n:i64=0;
 for b in 112 { row=[0;14];row[b/8]=(1<<(7-b%8)) as! u8;bit[b]=crc(row); }
 for a in 112 {
  patterns[n]=Pattern {bit[a],a as i32,-1};n++;
  for b in a+1..112 {patterns[n]=Pattern {bit[a]^bit[b],a as i32,b as i32};n++;}
 }
 sort(patterns) { a,b => a.key < b.key };
 for f in 41 { for j in 8 {let a=-2.0*PI*(-100000.0+5000.0*(f as f64))*(preamble[j] as f64)/4000000.0;carriers[8*f+j]=Complex {cos(a),sin(a)};} }
}
fn quantile(values: f64[:], fraction:f64) -> f64 {
 sort(values) {a,b => a<b};
 let index=((values.len-1) as f64)*fraction;let lo=index as i64;let hi=ceil(index) as i64;
 values[lo]+(values[hi]-values[lo])*(index-(lo as f64))
}
fn fit(x:const f64[:],y:const f64[:],w:const f64[:],use:const i64[:],filtered:bool) -> f64,f64,bool {
 var sw=0.0;var sx=0.0;var sy=0.0;
 for k in x.len {if !filtered || use[k]!=0 {let q=w[k]*w[k];sw+=q;sx+=q*x[k];sy+=q*y[k];}}
 if sw<=0.0 {return 0.0,0.0,false;}
 let mx=sx/sw;let my=sy/sw;var num=0.0;var den=0.0;
 for k in x.len {if !filtered || use[k]!=0 {let q=w[k]*w[k];let dx=x[k]-mx;num+=q*dx*(y[k]-my);den+=q*dx*dx;}}
 if den<=1.0e-30 {return 0.0,0.0,false;}
 let slope=num/den;return slope,my-slope*mx,true;
}
fn decode(logits:const f64[:],confidence:const f64[:],row:u8[:],flips:i8[:]) -> u8 {
 for j in 14 {row[j]=0;}flips[0]=-1;flips[1]=-1;
 for b in 112 {if logits[b]>0.0 {row[b/8] |= (1<<(7-b%8)) as! u8;}}
 if (row[0]>>3)!=17 {return 0;}
 let syndrome=crc(row);if syndrome==0 {return 1;}
 var lo:i64=0;var hi:i64=6328;
 while lo<hi {let m=lo+(hi-lo)/2;if patterns[m].key<syndrome {lo=m+1;}else{hi=m;}}
 if lo==6328 || patterns[lo].key!=syndrome {return 0;}
 var least:i64[6]=[-1;6];
 for b in 32..112 {for j in 6 {if least[j]<0 || confidence[b]<confidence[least[j]] {
  var q:i64=5;while q>j {least[q]=least[q-1];q--;}
  least[j]=b;break;
 }}}
 let bits:i64[2]=[patterns[lo].a,patterns[lo].b];
 for i in 2 {if bits[i]>=0 {var allowed=false;for j in 6 {if least[j]==bits[i] && confidence[bits[i]]<=0.35 {allowed=true;}}if !allowed {return 0;}}}
 for i in 2 {if bits[i]>=0 {row[bits[i]/8] ^= (1<<(7-bits[i]%8)) as! u8;flips[i]=bits[i] as! i8;}}
 return 1;
}
export fn goose_coherent(iq:const f32[:],starts:const i64[:],logits:f64[:],confidence:f64[:],tracked:u8[:],frequency:f64[:],inliers:i32[:],rows:u8[:],flips:i8[:],valid:u8[:]) {
 let n=starts.len;
 assert(n<=4096 && logits.len>=112*n && confidence.len>=112*n && tracked.len>=n && frequency.len>=n && inliers.len>=n && rows.len>=14*n && flips.len>=2*n && valid.len>=n);
 for k in n {
  let at=starts[k];assert(at>=0 && 2*(at+480)<=iq.len);let z=iq[2*at..2*(at+480)];let l=logits[112*k..112*(k+1)];let c=confidence[112*k..112*(k+1)];
  var p:f32[480]=[0.0;480];var positions:i64[112]=[0;112];var magn:f64[112]=[0.0;112];var sorted:f64[112]=[0.0;112];
  for q in 480 {let a=hypot32(z[2*q],z[2*q+1]);p[q]=a*a;}
  for b in 112 {let q=32+4*b;let left=p[q]+p[q+1];let right=p[q+2]+p[q+3];l[b]=left-right;c[b]=abs32(left-right)/(left+right+1.0e-9 as f32);positions[b]=q+(if l[b]>0.0 {0}else{2});}
  var selected:i64=0;var best=-1.0;
  for f in 41 {var a=Complex {0.0,0.0};for j in 8 {let q=preamble[j];a=add(a,mul(Complex {z[2*q],z[2*q+1]},carriers[8*f+j]));}let power=a.re*a.re+a.im*a.im;if power>best {best=power;selected=f;}}
  let coarse=-100000.0+(selected as f64)*5000.0;var omega=2.0*PI*coarse/4000000.0;
  var rotated:Complex[480]=[Complex {0.0,0.0};480];var oscillator=Complex {1.0,0.0};var step=Complex {cos(omega),-sin(omega)};
  for q in 480 {rotated[q]=mul(Complex {z[2*q],z[2*q+1]},oscillator);oscillator=mul(oscillator,step);}
  for b in 112 {let q=positions[b];let a=add(rotated[q],rotated[q+1]);magn[b]=magnitude(Complex {a.re*0.5,a.im*0.5});sorted[b]=magn[b];}
  let cutoff=quantile(sorted,0.35);var x:f64[112]=[0.0;112];var y:f64[112]=[0.0;112];var weights:f64[112]=[0.0;112];var mw:f64[112]=[0.0;112];var good:i64[112]=[0;112];var use:i64[112]=[0;112];var count:i64=0;var previous=0.0;var unwrapped=0.0;
  for b in 112 {if c[b]>=0.5 && magn[b]>=cutoff {
   let q=positions[b];let a=add(rotated[q],rotated[q+1]);let angle=atan2(a.im,a.re);
   if count!=0 {var delta=angle-previous;if delta>PI {delta-=2.0*PI;}else if delta< -PI {delta+=2.0*PI;}unwrapped+=delta;}else{unwrapped=angle;}
   previous=angle;x[count]=(q as f64)+0.5;y[count]=unwrapped;good[count]=q;weights[count]=magn[b];mw[count]=magn[b];count++;
  }}
  tracked[k]=0;frequency[k]=0.0/0.0;inliers[k]=0;
  if count>=24 {
   let cap=2.0*quantile(mw[..count],0.5);
   for j in count {weights[j]=min64(weights[j],cap);}
   var slope,intercept,ok=fit(x[..count],y[..count],weights[..count],use[..count],false);
   if ok {
    var kept:i64=0;
    for j in count {let r=y[j]-slope*x[j]-intercept;use[j]=if abs64(atan2(sin(r),cos(r)))<0.8 {1}else{0};kept+=use[j];}
    if kept>=24 {let a,b,passed=fit(x[..count],y[..count],weights[..count],use[..count],true);if passed {slope=a;intercept=b;}}
    if !is_nan(slope) && !is_inf(slope) && !is_nan(intercept) && !is_inf(intercept) && abs64(slope*4000000.0/(2.0*PI))<=30000.0 {
     tracked[k]=1;frequency[k]=coarse+slope*4000000.0/(2.0*PI);inliers[k]=kept as i32;
     omega+=slope;step=Complex {cos(omega),-sin(omega)};oscillator=Complex {cos(intercept),-sin(intercept)};
     for q in 480 {rotated[q]=mul(Complex {z[2*q],z[2*q+1]},oscillator);oscillator=mul(oscillator,step);}
     var shape:Complex[2]=[Complex {0.0,0.0};2];
     for j in count {shape[0]=add(shape[0],rotated[good[j]]);shape[1]=add(shape[1],rotated[good[j]+1]);}
     for i in 2 {shape[i]=Complex {shape[i].re/(count as f64),-shape[i].im/(count as f64)};}
     for b in 112 {let q=32+4*b;let left=add(mul(rotated[q],shape[0]),mul(rotated[q+1],shape[1])).re;let right=add(mul(rotated[q+2],shape[0]),mul(rotated[q+3],shape[1])).re;l[b]=left-right;c[b]=abs64(l[b])/(abs64(left)+abs64(right)+1.0e-9);}
    }
   }
  }
  valid[k]=decode(l,c,rows[14*k..14*(k+1)],flips[2*k..2*(k+1)]);
 }
}
// Attribution-only control: allow C's quantile to use this same typed sort.
export fn goose_sort(values:f64[:]) { sort(values) {a,b => a<b}; }

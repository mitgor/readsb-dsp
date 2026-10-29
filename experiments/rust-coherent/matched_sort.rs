// SPDX-License-Identifier: Apache-2.0
// Rust adaptation of the same Goose v2026.3 typed sort as coherent_sort.h.
// Original: aardappel/goose acc6310a83df7a322d3f8264a808f675348c4260,
// stdlib/std.goose; Apache-2.0 license in docs/licenses/GOOSE-APACHE-2.0.txt.
fn insertion(a:&mut[f64]){for i in 1..a.len(){let x=a[i];let mut j=i;while j>0&&x<a[j-1]{a[j]=a[j-1];j-=1;}a[j]=x;}}
fn sift(a:&mut[f64],mut root:usize){while 2*root+1<a.len(){let mut child=2*root+1;if child+1<a.len()&&a[child]<a[child+1]{child+=1;}if !(a[root]<a[child]){break;}a.swap(root,child);root=child;}}
fn heap(a:&mut[f64]){for i in (0..a.len()/2).rev(){sift(a,i);}for end in (1..a.len()).rev(){a.swap(0,end);sift(&mut a[..end],0);}}
fn median3(a:&[f64],i:usize,j:usize,k:usize)->usize{let x=a[i]<a[j];if x!=(a[i]<a[k]){return i;}if (a[j]<a[k])!=x{return k;}j}
fn partition(a:&mut[f64],equal:bool)->usize{let pivot=a[0];let mut lt=1;for i in 1..a.len(){let x=a[i];a[i]=a[lt];a[lt]=x;lt+=if equal{!(pivot<x)}else{x<pivot} as usize;}lt-1}
pub(super)fn sort(a:&mut[f64]){
 let n=a.len();if n>112||a.iter().any(|x|!x.is_finite()){unsafe{super::qsort(a.as_mut_ptr() as *mut super::c_void,n,8,super::compare_double);}return;}
 if n<=10{insertion(a);return;}
 let mut run=2;if a[1]<a[0]{while run<n&&a[run]<a[run-1]{run+=1;}a[..run].reverse();}else{while run<n&&!(a[run]<a[run-1]){run+=1;}}if run==n{return;}
 let mut limit=0;let mut x=n;while x>1{x>>=1;limit+=2;}
 let mut stack=[0usize;32];let mut top=0;let mut lo=0;let mut hi=n;
 loop{
  let size=hi-lo;
  if size>10&&limit>0{
   limit-=1;let eighth=size/8;let p=median3(&a[lo..hi],0,4*eighth,7*eighth);a[lo..hi].swap(0,p);
   if lo>0&&!(a[lo-1]<a[lo]){let m=partition(&mut a[lo..hi],true);a[lo..hi].swap(0,m);lo+=m+1;continue;}
   let m=partition(&mut a[lo..hi],false);a[lo..hi].swap(0,m);
   if m<size-1-m{stack[top]=lo+m+1;stack[top+1]=hi;stack[top+2]=limit;top+=3;hi=lo+m;}
   else{stack[top]=lo;stack[top+1]=lo+m;stack[top+2]=limit;top+=3;lo+=m+1;}continue;
  }
  if size>10{heap(&mut a[lo..hi]);}else{insertion(&mut a[lo..hi]);}
  if top==0{return;}top-=1;limit=stack[top];top-=1;hi=stack[top];top-=1;lo=stack[top];
 }
}
#[cfg(test)]
mod tests{
 #[test]fn sort_cases(){
  let mut state=20261029u64;
  for trial in 0..200000{
   let n=trial%113;let mut a=[0f64;112];
   for j in 0..n{state^=state<<13;state^=state>>7;state^=state<<17;a[j]=match(trial/113)%7{0=>j as f64,1=>-(j as f64),2=>1.0,3=>(state%5) as f64,4=>(if j<n/2{j}else{n-j}) as f64,_=>(state as u32 as i32) as f64/65536.0};}
   let mut b=a;super::sort(&mut a[..n]);b[..n].sort_unstable_by(|a,b|a.partial_cmp(b).unwrap());assert_eq!(&a[..n],&b[..n]);
  }
 }
}

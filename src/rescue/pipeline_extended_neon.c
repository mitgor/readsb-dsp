/* Offline-only AArch64 acquisition-score experiment. The live V3 library is
 * included unchanged for a byte-exact reference and separate candidate API. */
#include "pipeline_v3.c"
#if defined(__aarch64__)
#include <arm_neon.h>
#endif

int rescue_extended_scores_neon(const float *p,int64_t n,double onweight,
                                double offweight,double norm2,double *out){
#if !defined(__aarch64__)
 return rescue_extended_scores(p,n,onweight,offweight,norm2,out);
#else
 if(n<52||!isfinite(norm2)||norm2<=0)return -1;
 const int on[18]={0,1,4,5,14,15,18,19,32,33,38,39,42,43,46,47,48,49};
 double total=0,square=0;
 for(int k=0;k<52;k++){total+=p[k];square+=(double)p[k]*p[k];}
 int64_t i=0;
 for(;i+3<=n-52;i+=4){
  float64x2_t sum01=vdupq_n_f64(0),sum23=vdupq_n_f64(0);
  for(int k=0;k<18;k++){
   float32x4_t samples=vld1q_f32(p+i+on[k]);
   sum01=vaddq_f64(sum01,vcvt_f64_f32(vget_low_f32(samples)));
   sum23=vaddq_f64(sum23,vcvt_f64_f32(vget_high_f32(samples)));
  }
  double sums[4];vst1q_f64(sums,sum01);vst1q_f64(sums+2,sum23);
  for(int lane=0;lane<4;lane++){
   int64_t q=i+lane;
   if(q){double old=p[q-1],fresh=p[q+51];total+=fresh-old;square+=fresh*fresh-old*old;}
   double onpower=sums[lane];
   out[q]=(onweight*onpower+offweight*(total-onpower))/sqrt(fmax(square,1.e-12)*norm2);
  }
 }
 for(;i<=n-52;i++){
  if(i){double old=p[i-1],fresh=p[i+51];total+=fresh-old;square+=fresh*fresh-old*old;}
  double onpower=0;for(int k=0;k<18;k++)onpower+=p[i+on[k]];
  out[i]=(onweight*onpower+offweight*(total-onpower))/sqrt(fmax(square,1.e-12)*norm2);
 }
 return 0;
#endif
}

/* Preserve the existing peak-distance rule and stable score ranking while
 * avoiding Python masks, sorts and an exported full-length score array. */
int64_t rescue_extended_select_neon(const float *p,int64_t n,int64_t core,
                                    double onweight,double offweight,double norm2,
                                    int budget,int64_t *out_ids,double *out_score){
 if(n<52||n>10000051||core<0||budget<1||budget>256||!out_ids||!out_score)return -1;
 int64_t length=n-51;
 double *scores=malloc((size_t)length*sizeof(double));
 int64_t *peaks=malloc((size_t)length*sizeof(int64_t));
 if(!scores||!peaks){free(scores);free(peaks);return -1;}
 if(rescue_extended_scores_neon(p,n,onweight,offweight,norm2,scores)){
  free(scores);free(peaks);return -1;
 }
 int64_t found=rescue_fast_peaks(scores,length,.30,peaks);
 if(found<0){free(scores);free(peaks);return found;}
 int64_t count=0;
 for(int64_t j=0;j<found;j++){
  int64_t pos=peaks[j];
  if(pos<8||pos>=core||pos+488>=n)continue;
  double score=scores[pos];
  int at=0;
  while(at<count&&out_score[at]>=score)at++;
  if(at>=budget)continue;
  if(count<budget)count++;
  for(int k=(int)count-1;k>at;k--){out_ids[k]=out_ids[k-1];out_score[k]=out_score[k-1];}
  out_ids[at]=pos;out_score[at]=score;
 }
 free(scores);free(peaks);return count;
}

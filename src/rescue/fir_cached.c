/* Worker-local FIR tap/schedule cache. Frozen lane arithmetic and edge policy.
 * No global state, RF I/O, FMA contraction or fast-math. */
#include <stdint.h>
#include <math.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif
int rescue_fir_prepare(const float *h,int64_t first,float *packed,float *reverse,int64_t *phases,int64_t *indices){
 if(first<0||first>INT64_MAX/3-10000000)return -1;
 for(int j=0;j<102;j++)if(!isfinite(h[j]))return -1;
 for(int p=0;p<5;p++){
  for(int j=0;j<24;j++)packed[24*p+j]=0;
  for(int j=p,k=0;j<102;j+=5,k++)packed[24*p+k]=h[j];
  for(int j=0;j<24;j+=4)for(int k=0;k<4;k++)reverse[24*p+j+k]=packed[24*p+j+3-k];
 }
 for(int k=0;k<5;k++){int64_t t=(first+k)*3+51;phases[k]=t%5;indices[k]=(t-phases[k])/5;}
 return 0;
}
static inline void fir_sample(const float *src,int64_t n,int64_t index,int phase,const float *packed,const float *reverse,float *out){
 if(index<23||index>=n){
  float r=0,i=0;int count=phase<2?21:20;
  for(int k=0;k<count;k++,index--)if(index>=0&&index<n){r+=packed[24*phase+k]*src[2*index];i+=packed[24*phase+k]*src[2*index+1];}
  out[0]=r;out[1]=i;return;
 }
#if defined(__ARM_NEON)
 float32x4_t ar=vdupq_n_f32(0),ai=vdupq_n_f32(0);
 for(int j=0;j<24;j+=4,index-=4){
  float32x4_t coeff=vld1q_f32(reverse+24*phase+j);
  float32x4x2_t iq=vld2q_f32(src+2*(index-3));
  ar=vmlaq_f32(ar,iq.val[0],coeff);ai=vmlaq_f32(ai,iq.val[1],coeff);
 }
 out[0]=vaddvq_f32(ar);out[1]=vaddvq_f32(ai);
#else
 (void)reverse;float ar[4]={0},ai[4]={0};
 for(int j=0;j<24;j+=4,index-=4)for(int q=0;q<4;q++){
  ar[q]+=packed[24*phase+j+q]*src[2*(index-q)];ai[q]+=packed[24*phase+j+q]*src[2*(index-q)+1];
 }
 out[0]=(ar[0]+ar[1])+(ar[2]+ar[3]);out[1]=(ai[0]+ai[1])+(ai[2]+ai[3]);
#endif
}
int rescue_fir_cached(const float *src,int64_t n,int64_t count,const float *packed,const float *reverse,const int64_t *phases,const int64_t *indices,float *out){
 if(n<0||n>100000000||count<0||count>10000000)return -1;
 for(int k=0;k<5;k++)if(phases[k]<0||phases[k]>=5||indices[k]<0||indices[k]>INT64_MAX-10000000)return -1;
 int64_t k=0,base=0;
 for(;k+4<count;k+=5,base+=3){
  for(int q=0;q<5;q++)fir_sample(src,n,indices[q]+base,(int)phases[q],packed,reverse,out+2*(k+q));
 }
 for(int q=0;k<count;k++,q++)fir_sample(src,n,indices[q]+base,(int)phases[q],packed,reverse,out+2*k);
 return 0;
}

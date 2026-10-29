/* Isolated fused native header and normalized energy preparation. The scalar
 * reference is included to preserve CRC and exact header reduction semantics. */
#include <string.h>
#include "frontend.c"
int rescue_candidate_prepare(const float *iq,int64_t length,const int64_t *starts,int64_t n,uint8_t *headers,uint8_t *rows,uint8_t *valid) {
 const int on[8]={0,1,4,5,14,15,18,19};const int df17[5]={1,0,0,0,1};
 if(n<0||n>8192||length<480)return -1;
 for(int64_t k=0;k<n;k++) {
  int64_t s=starts[k];if(s<0||s>length-480)return -1;
  float p[480],sequential=0,a[8];
  for(int j=0;j<8;j++){float x=iq[2*(s+on[j])],y=iq[2*(s+on[j])+1];if(!isfinite(x)||!isfinite(y))return -1;float q=hypotf(x,y);a[j]=q*q;sequential+=power_at(iq,s+on[j]);}
  sequential=fmaxf(sequential/8.f,1.e-5f);headers[k]=1;valid[k]=0;memset(rows+14*k,0,14);
  for(int b=0;b<5;b++) {
   int q=32+4*b;
   float left=fminf(power_at(iq,s+q)/sequential,12.f)+fminf(power_at(iq,s+q+1)/sequential,12.f);
   float right=fminf(power_at(iq,s+q+2)/sequential,12.f)+fminf(power_at(iq,s+q+3)/sequential,12.f);
   if((left>right)!=df17[b]){headers[k]=0;break;}
  }
  if(!headers[k])continue;
  for(int q=0;q<480;q++){float x=iq[2*(s+q)],y=iq[2*(s+q)+1];if(!isfinite(x)||!isfinite(y))return -1;float v=hypotf(x,y);p[q]=v*v;}
  float scale=fmaxf(((a[0]+a[1])+(a[2]+a[3])+(a[4]+a[5])+(a[6]+a[7]))/8.f,1.e-5f);
  uint8_t *row=rows+14*k;
  for(int b=0;b<112;b++){int q=32+4*b;float left=fminf(p[q]/scale,12.f)+fminf(p[q+1]/scale,12.f),right=fminf(p[q+2]/scale,12.f)+fminf(p[q+3]/scale,12.f);row[b/8]|=(left>right)<<(7-b%8);}
  valid[k]=rescue_row_ok(row);
 }
 return 0;
}

/* Block-local dense catalog. State and rows are caller-owned reusable buffers;
 * no allocator, global mutable state, or cross-epoch reuse. */
int64_t rescue_cached_header(const float *iq,int64_t length,const int64_t *starts,int64_t n,uint8_t *state,int64_t *ids,int64_t *computed){
 if(n<0||n>8192||length<480)return -1;int64_t count=0;*computed=0;
 for(int64_t k=0;k<n;k++){
  int64_t at=starts[k];if(at<0||at>length-480)return -1;
  if(!(state[at]&1)){int64_t id;int64_t good=rescue_header_ids(iq,starts+k,1,&id);state[at]|=1|(good?2:0);(*computed)++;}
  if(state[at]&2)ids[count++]=k;
 }
 return count;
}
int64_t rescue_cached_energy(const float *iq,int64_t length,const int64_t *starts,int64_t n,uint8_t *state,uint8_t *cache_rows,uint8_t *cache_valid,uint8_t *rows,uint8_t *valid){
 if(n<0||n>8192||length<480)return -1;int64_t computed=0;
 for(int64_t k=0;k<n;k++){
  int64_t at=starts[k];if(at<0||at>length-480)return -1;
  if(!(state[at]&4)){rescue_baseline(iq,starts+k,1,cache_rows+14*at,cache_valid+at);state[at]|=4;computed++;}
  memcpy(rows+14*k,cache_rows+14*at,14);valid[k]=cache_valid[at];
 }
 return computed;
}

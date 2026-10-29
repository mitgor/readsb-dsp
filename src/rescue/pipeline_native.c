/* Offline native orchestration helpers; frozen kernels keep their arithmetic. */
#include "research_sequence.c"
/* Native peak selection with exact SciPy fallback for equal priorities. */
int64_t rescue_fast_peaks(const double *score,int64_t n,double threshold,int64_t *out){
 if(n<3||n>10000000)return -1;
 Peak *peaks=malloc(sizeof(Peak)*n);uint8_t *masked=calloc(n,1);
 if(!peaks||!masked){free(peaks);free(masked);return -1;}
 int64_t count=0;
 for(int64_t j=1;j<n-1;j++)if(score[j]>=threshold&&score[j]>score[j-1]){
  int64_t end=j;while(end+1<n&&score[end+1]==score[j])end++;
  if(end<n-1&&score[end]>score[end+1])peaks[count++]=(Peak){score[j],(j+end)/2};j=end;
 }
 qsort(peaks,count,sizeof(Peak),by_score);
 for(int64_t j=1;j<count;j++)if(peaks[j].score==peaks[j-1].score){free(peaks);free(masked);return -2;}
 int64_t keep=0;
 for(int64_t j=0;j<count;j++){
  int64_t pos=peaks[j].position;if(masked[pos])continue;
  for(int t=-2;t<=2;t++)if(pos+t>=0&&pos+t<n)masked[pos+t]=1;
  peaks[keep++]=peaks[j];
 }
 qsort(peaks,keep,sizeof(Peak),by_position);
 for(int64_t j=0;j<keep;j++)out[j]=peaks[j].position;
 free(peaks);free(masked);return keep;
}
/* Convert UC8 once, with exact power-of-two normalization and zero RF halos.
   The frozen platform FIR remains responsible for SIMD summation order. */
int rescue_fast_convert(const uint8_t *raw,int64_t n,int64_t left,int64_t right,float *out){
 if(n<0||left<0||right<0||n+left+right>10000000)return -1;
 memset(out,0,2*left*sizeof(float));
 for(int64_t j=0;j<2*n;j++)out[2*left+j]=((float)raw[j]-127.5f)/128.f;
 memset(out+2*(left+n),0,2*right*sizeof(float));return 0;
}
/* Lookup-first <=2 weak-bit correction, identical stable confidence ranking.
   Caller supplies unchanged NumPy logits/confidences (no abs rounding drift). */
int64_t rescue_fast_soft(const float *l,const float *c,int64_t n,float limit,int k,int header,int64_t *ids,uint8_t *rows,int8_t *flips,int64_t *hyp){
 if(n<0||n>4096||k<1||k>112||!isfinite(limit))return -1;
 int64_t count=0;*hyp=0;
 for(int64_t j=0;j<n;j++){
  uint8_t row[14]={0};for(int b=0;b<112;b++)if(l[112*j+b]>0)row[b/8]|=1<<(7-b%8);
  uint32_t s=crc(row);if(!s)continue;int lo=0,hi=6328;
  while(lo<hi){int m=(lo+hi)/2;if(patterns[m].key<s)lo=m+1;else hi=m;}
  if(lo==6328||patterns[lo].key!=s)continue;
  Pattern p=patterns[lo];row[p.a/8]^=1<<(7-p.a%8);if(p.b>=0)row[p.b/8]^=1<<(7-p.b%8);
  if(row[0]>>3!=17)continue;
  int rank[112],used=0;
  for(int b=0;b<112;b++)if(b>=32||(header&&b<5)){
   int q=used;while(q>0&&c[j*112+b]<c[j*112+rank[q-1]]){rank[q]=rank[q-1];q--;}rank[q]=b;used++;
  }
  int a=0,b=p.b<0,allowed=0;
  for(int q=0;q<used&&q<k;q++)if(c[j*112+rank[q]]<=limit){allowed++;a|=rank[q]==p.a;b|=rank[q]==p.b;}
  if(a&&b){ids[count]=j;memcpy(rows+14*count,row,14);flips[2*count]=p.a;flips[2*count+1]=p.b;count++;*hyp+=allowed*(allowed+1)/2;}
 }
 return count;
}

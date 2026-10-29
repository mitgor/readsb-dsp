/* Isolated exact-arithmetic optimization; no I/O or admission policy. */
#define rescue_sequence_batch rescue_sequence_batch_reference
#define rescue_extended_scores rescue_extended_scores_reference
#include "pipeline_native.c"
#undef rescue_sequence_batch
#undef rescue_extended_scores
static void seq_prepared_v3(const float *window,double freq,const double *templates,const double *pre,double *l,double *c){
 const float *z=window+16;double w=freq*2*PI/RATE;double complex g=0;double den=0;
 for(int n=4;n<28;n++){double complex p=pre[2*(n-4)]+I*pre[2*(n-4)+1];int q=8+n-4;double complex y=sf_rot(window[2*q]+I*(double)window[2*q+1],w,n-4-240);g+=conj(p)*y;den+=creal(p*conj(p));}g/=fmax(den,1.e-12);
 double complex scaled[5][4][2][4];const int block[5]={0,1,2,112,113};
 for(int k=0;k<5;k++)for(int s=0;s<4;s++)for(int v=0;v<2;v++)for(int t=0;t<4;t++){
  int q=2*(((block[k]*4+s)*2+v)*4+t);scaled[k][s][v][t]=g*(templates[q]+I*templates[q+1]);
 }
 double cost[114][4][2],a[115][4],back[115][4];int trace[114][4];
 for(int s=0;s<4;s++){a[0][s]=s?1.e100:0;back[114][s]=0;}
 for(int b=0;b<114;b++){
  double complex obs[4];for(int t=0;t<4;t++){int n=32+4*b+t,q=8+n-4;obs[t]=sf_rot(window[2*q]+I*(double)window[2*q+1],w,n-4-240);}
  for(int s=0;s<4;s++)a[b+1][s]=1.e100;
  for(int s=0;s<4;s++)for(int v=0;v<2;v++){double e=0;for(int t=0;t<4;t++){int k=b<2?b:(b<112?2:b-109);double complex d=obs[t]-scaled[k][s][v][t];e+=creal(d*conj(d));}if(b>=112&&v)e=1.e100;cost[b][s][v]=e;int next=((s&1)<<1)|v;if(a[b][s]+e<a[b+1][next]){a[b+1][next]=a[b][s]+e;trace[b][next]=s;}}
 }
 for(int b=113;b>=0;b--)for(int s=0;s<4;s++)back[b][s]=fmin(cost[b][s][0]+back[b+1][(s&1)<<1],cost[b][s][1]+back[b+1][((s&1)<<1)|1]);
 int state=0;for(int s=1;s<4;s++)if(a[114][s]<a[114][state])state=s;int bits[114];for(int b=113;b>=0;b--){bits[b]=state&1;state=trace[b][state];}
 double noise=sf_noise(z);
 for(int b=0;b<112;b++){double best[2]={1.e100,1.e100};for(int s=0;s<4;s++)for(int v=0;v<2;v++){int next=((s&1)<<1)|v;double x=a[b][s]+cost[b][s][v]+back[b+1][next];if(x<best[v])best[v]=x;}double strength=fabs(best[0]-best[1]);l[b]=(bits[b]?1:-1)*fmax(strength,1.e-20);c[b]=1-exp(-strength/fmax(4*noise,1.e-12));}
}
int rescue_sequence_batch(const float *iq,int64_t length,const int64_t *starts,int64_t count,const double *seeds,const double *templates,const double *pre,double *l,double *c,uint8_t *rows,int8_t *flips,uint8_t *valid){
 if(length<496||count<0||count>4096)return -1;
 for(int64_t j=0;j<count;j++)if(starts[j]<8||starts[j]+488>length)return -1;
 /* Generic templates remain supported; only identical interior blocks share work. */
 int repeat=1;for(int b=3;b<112;b++)if(memcmp(templates+64*b,templates+128,64*sizeof(double))){repeat=0;break;}
 if(!repeat)return rescue_sequence_batch_reference(iq,length,starts,count,seeds,templates,pre,l,c,rows,flips,valid);
 for(int64_t j=0;j<count;j++){const float *window=iq+2*(starts[j]-8);double freq=sf_seed(window+16,seeds[j]);seq_prepared_v3(window,freq,templates,pre,l+112*j,c+112*j);valid[j]=decode(l+112*j,c+112*j,rows+14*j,flips+2*j);}
 return 0;
}
/* Four independent lanes preserve each sample's 18-term addition order.
   Rolling total/square and normalization stay scalar in their original order. */
int rescue_extended_scores(const float *p,int64_t n,double onweight,double offweight,double norm2,double *out){
 if(n<52||!isfinite(norm2)||norm2<=0)return -1;
 const int on[18]={0,1,4,5,14,15,18,19,32,33,38,39,42,43,46,47,48,49};double total=0,square=0;
 for(int k=0;k<52;k++){total+=p[k];square+=(double)p[k]*p[k];}
 int64_t i=0;
 for(;i+3<=n-52;i+=4){
  double sums[4]={0,0,0,0};
  for(int k=0;k<18;k++)for(int lane=0;lane<4;lane++)sums[lane]+=(double)p[i+lane+on[k]];
  for(int lane=0;lane<4;lane++){
   int64_t q=i+lane;if(q){double old=p[q-1],fresh=p[q+51];total+=fresh-old;square+=fresh*fresh-old*old;}
   double onpower=sums[lane];out[q]=(onweight*onpower+offweight*(total-onpower))/sqrt(fmax(square,1.e-12)*norm2);
  }
 }
 for(;i<=n-52;i++){
  if(i){double old=p[i-1],fresh=p[i+51];total+=fresh-old;square+=fresh*fresh-old*old;}
  double onpower=0;for(int k=0;k<18;k++)onpower+=p[i+on[k]];
  out[i]=(onweight*onpower+offweight*(total-onpower))/sqrt(fmax(square,1.e-12)*norm2);
 }
 return 0;
}

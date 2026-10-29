/* Saved-RF experiments only. No live linkage, sockets or payload priors. */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#define MAXN 1600
int overlap_project(const float *z,int n,const double *w,int mode,float *out){
 if(n<480||n>MAXN||mode<0||mode>1)return -1;
 for(int t=0;t<n;t++){
  double y=w[4];
  for(int k=0;k<2;k++){int q=t-k;if(q>=0)y+=w[2*k]*z[2*q]+w[2*k+1]*z[2*q+1];}
  out[t]=(float)y;
 }return 0;
}
static int pulse(int t,int start,int bit,int value){int q=t-start-32-4*bit;return q>=0&&q<4&&((q<2)==value);}
static void atom(int t,int start,int bit,int value,const float *carrier,double *re,double *im){
 int q=t-start;if(pulse(t,start,bit,value)){*re=carrier[2*q];*im=carrier[2*q+1];}else{*re=0;*im=0;}
}
int overlap_joint(const float *z,int n,const int *starts,const float *carriers,const uint8_t *initial,int iterations,float *logits){
 if(n<480||n>MAXN||iterations<1||iterations>3)return -1;
 for(int s=0;s<2;s++)if(starts[s]<0||starts[s]+480>n)return -1;
 double r[2*MAXN];uint8_t bits[224];for(int j=0;j<224;j++)bits[j]=initial[j]>0;
 for(int t=0;t<n;t++){r[2*t]=z[2*t];r[2*t+1]=z[2*t+1];}
 const int pre[8]={0,1,4,5,14,15,18,19};
 for(int s=0;s<2;s++){
  const float *c=carriers+s*960;
  for(int k=0;k<8;k++){int q=pre[k],t=starts[s]+q;r[2*t]-=c[2*q];r[2*t+1]-=c[2*q+1];}
  for(int b=0;b<112;b++)for(int k=0;k<4;k++){int t=starts[s]+32+4*b+k;double re,im;atom(t,starts[s],b,bits[s*112+b],c,&re,&im);r[2*t]-=re;r[2*t+1]-=im;}
 }
 for(int j=0;j<224;j++)logits[j]=bits[j]?1:-1;
 for(int pass=0;pass<iterations;pass++)for(int b=0;b<112;b++){
  int j=(int)floor((starts[0]+4.0*b-starts[1])/4.0);int valid=j>=0&&j<112;
  int old0=bits[b],old1=valid?bits[112+j]:0;
  int lo=starts[0]+32+4*b,hi=lo+4;
  if(valid){int q=starts[1]+32+4*j;if(q<lo)lo=q;if(q+4>hi)hi=q+4;}
  double cost[4]={0};
  for(int t=lo;t<hi;t++){
   double a,bv,c=0,d=0;atom(t,starts[0],b,old0,carriers,&a,&bv);if(valid)atom(t,starts[1],j,old1,carriers+960,&c,&d);
   double re=r[2*t]+a+c,im=r[2*t+1]+bv+d;
   for(int v=0;v<4;v++){double ar,ai,br=0,bi=0;atom(t,starts[0],b,v/2,carriers,&ar,&ai);if(valid)atom(t,starts[1],j,v%2,carriers+960,&br,&bi);double x=re-ar-br,y=im-ai-bi;cost[v]+=x*x+y*y;}
  }
  int best=0;for(int v=1;v<4;v++)if(cost[v]<cost[best])best=v;
  bits[b]=best/2;if(valid)bits[112+j]=best%2;
  logits[b]=(float)(fmin(cost[0],cost[1])-fmin(cost[2],cost[3]));
  if(valid)logits[112+j]=(float)(fmin(cost[0],cost[2])-fmin(cost[1],cost[3]));
  for(int t=lo;t<hi;t++){
   double ar,ai,br=0,bi=0,nr,ni,mr=0,mi=0;atom(t,starts[0],b,old0,carriers,&ar,&ai);if(valid)atom(t,starts[1],j,old1,carriers+960,&br,&bi);atom(t,starts[0],b,bits[b],carriers,&nr,&ni);if(valid)atom(t,starts[1],j,bits[112+j],carriers+960,&mr,&mi);r[2*t]+=ar+br-nr-mr;r[2*t+1]+=ai+bi-ni-mi;
  }
 }
 /* Sign consistency includes secondary bits outside paired overlap. */
 for(int b=0;b<224;b++)if((logits[b]>0)!=bits[b])logits[b]=bits[b]?fabsf(logits[b])+1e-8f:-fabsf(logits[b])-1e-8f;
 return 0;
}

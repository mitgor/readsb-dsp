/* Offline, bounded joint PPM detector with explicit three-tap pulse response. */
#include <math.h>
#include <stdint.h>
#define MAX 1600
static void symbol(int t,int start,int bit,int value,const float *rotation,const float *h,double *re,double *im){
 double ar=0,ai=0;
 for(int k=0;k<3;k++){
  int q=t-start-(k-1)-32-4*bit;
  if(q>=0&&q<4&&((q<2)==value)){ar+=h[2*k];ai+=h[2*k+1];}
 }
 double x=rotation[2*t],y=rotation[2*t+1];*re=ar*x-ai*y;*im=ar*y+ai*x;
}
int joint_channel_decode(const float *z,int n,const int *starts,const float *rot,const float *taps,const uint8_t *initial,int iterations,float *logits){
 if(n<484||n>MAX||iterations<1||iterations>3)return -1;
 for(int s=0;s<2;s++)if(starts[s]<2||starts[s]+482>n)return -1;
 for(int t=0;t<2*n;t++)if(!isfinite(z[t]))return -1;
 for(int t=0;t<4*n;t++)if(!isfinite(rot[t]))return -1;
 for(int t=0;t<12;t++)if(!isfinite(taps[t]))return -1;
 double r[2*MAX];uint8_t bits[224];for(int k=0;k<224;k++){bits[k]=initial[k]>0;logits[k]=bits[k]?1:-1;}
 for(int t=0;t<n;t++){r[2*t]=z[2*t];r[2*t+1]=z[2*t+1];}
 const int pre[8]={0,1,4,5,14,15,18,19};
 for(int s=0;s<2;s++){
  for(int j=0;j<8;j++)for(int k=0;k<3;k++){
   int t=starts[s]+pre[j]+k-1;double ar=taps[s*6+2*k],ai=taps[s*6+2*k+1],x=rot[s*2*n+2*t],y=rot[s*2*n+2*t+1];r[2*t]-=ar*x-ai*y;r[2*t+1]-=ar*y+ai*x;
  }
  for(int b=0;b<112;b++)for(int t=starts[s]+32+4*b-1;t<starts[s]+32+4*b+5;t++){
   double re,im;symbol(t,starts[s],b,bits[s*112+b],rot+s*2*n,taps+s*6,&re,&im);r[2*t]-=re;r[2*t+1]-=im;
  }
 }
 for(int pass=0;pass<iterations;pass++)for(int b=0;b<112;b++){
  int j=(int)floor((starts[0]+4.0*b-starts[1])/4.0),valid=j>=0&&j<112;int old0=bits[b],old1=valid?bits[112+j]:0;
  int lo=starts[0]+32+4*b-1,hi=lo+6;
  if(valid){int q=starts[1]+32+4*j-1;if(q<lo)lo=q;if(q+6>hi)hi=q+6;}
  double cost[4]={0};
  for(int t=lo;t<hi;t++){
   double ar,ai,br=0,bi=0;symbol(t,starts[0],b,old0,rot,taps,&ar,&ai);if(valid)symbol(t,starts[1],j,old1,rot+2*n,taps+6,&br,&bi);double re=r[2*t]+ar+br,im=r[2*t+1]+ai+bi;
   for(int v=0;v<4;v++){
    double cr,ci,dr=0,di=0;symbol(t,starts[0],b,v/2,rot,taps,&cr,&ci);if(valid)symbol(t,starts[1],j,v%2,rot+2*n,taps+6,&dr,&di);double x=re-cr-dr,y=im-ci-di;cost[v]+=x*x+y*y;
   }
  }
  int best=0;for(int v=1;v<4;v++)if(cost[v]<cost[best])best=v;
  bits[b]=best/2;if(valid)bits[112+j]=best%2;
  logits[b]=(float)(fmin(cost[0],cost[1])-fmin(cost[2],cost[3]));if(valid)logits[112+j]=(float)(fmin(cost[0],cost[2])-fmin(cost[1],cost[3]));
  for(int t=lo;t<hi;t++){
   double ar,ai,br=0,bi=0,cr,ci,dr=0,di=0;symbol(t,starts[0],b,old0,rot,taps,&ar,&ai);if(valid)symbol(t,starts[1],j,old1,rot+2*n,taps+6,&br,&bi);symbol(t,starts[0],b,bits[b],rot,taps,&cr,&ci);if(valid)symbol(t,starts[1],j,bits[112+j],rot+2*n,taps+6,&dr,&di);r[2*t]+=ar+br-cr-dr;r[2*t+1]+=ai+bi-ci-di;
  }
 }
 for(int b=0;b<224;b++)if((logits[b]>0)!=bits[b])logits[b]=bits[b]?fabsf(logits[b])+1e-8f:-fabsf(logits[b])-1e-8f;
 return 0;
}

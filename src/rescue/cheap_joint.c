/* Offline fixed-carrier/fixed-pulse two-source estimator. No CRC or RF I/O. */
#include <complex.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#define MAX 1024
#define PI 3.14159265358979323846
static double n2(double complex z){return creal(z)*creal(z)+cimag(z)*cimag(z);}
static int solve(double complex a[3][3],double complex b[3],double complex h[3]){
 for(int k=0;k<3;k++){
  int p=k;for(int j=k+1;j<3;j++)if(cabs(a[j][k])>cabs(a[p][k]))p=j;
  if(cabs(a[p][k])<1e-15)return -1;
  for(int j=0;j<3;j++){double complex v=a[k][j];a[k][j]=a[p][j];a[p][j]=v;}double complex v=b[k];b[k]=b[p];b[p]=v;
  for(int j=k+1;j<3;j++){v=a[j][k]/a[k][k];for(int t=k;t<3;t++)a[j][t]-=v*a[k][t];b[j]-=v*b[k];}
 }
 for(int k=2;k>=0;k--){h[k]=b[k];for(int j=k+1;j<3;j++)h[k]-=a[k][j]*h[j];h[k]/=a[k][k];}return 0;
}
static double complex bitwave(int t,int start,int bit,int value,const double complex *rot,const double complex *h){
 int q=t-start-32-4*bit+4;
 return q>=0&&q<12?h[12*value+q]*rot[t]:0;
}
static void waveform(double complex *a,int n,int start,const uint8_t *bits,const double complex *rot,const double complex *h,const double complex *pulse){
 memset(a,0,n*sizeof(*a));int pre[8]={0,1,4,5,14,15,18,19};
 for(int j=0;j<8;j++)for(int k=0;k<9;k++){int t=start+pre[j]+k-4;if(t>=0&&t<n)a[t]+=h[k]*rot[t];}
 for(int b=0;b<112;b++)for(int t=start+32+4*b-4;t<start+32+4*b+8&&t<n;t++)if(t>=0)a[t]+=bitwave(t,start,b,bits[b],rot,pulse);
}
static int fit(const double complex *z,double complex a[2][MAX],int n,double complex *gain,double *quality){
 double complex g[3][3]={{0}},rhs[3]={0};double normal=0;int nt=0;
 for(int t=0;t<n;t++){
  normal+=n2(z[t]);if(t%48>=24)continue;nt++;
  double complex x[3]={a[0][t],a[1][t],1};
  for(int j=0;j<3;j++){rhs[j]+=conj(x[j])*z[t];for(int k=0;k<3;k++)g[j][k]+=conj(x[j])*x[k];}
 }
 normal=fmax(normal/n,1e-12);double trace=creal(g[0][0]+g[1][1]+g[2][2]);double corr=n2(g[0][1])/fmax(creal(g[0][0])*creal(g[1][1]),1e-20);
 for(int j=0;j<3;j++)g[j][j]+=.001*fmax(trace/3,1e-9);
 if(solve(g,rhs,gain))return -1;
 double train=0,test=0,power[2]={0};int ne=0;
 for(int t=0;t<n;t++){
  double e=n2(z[t]-gain[2]-gain[0]*a[0][t]-gain[1]*a[1][t]);
  if(t%48<24)train+=e;if(t%48>=36&&t%48<44){test+=e;ne++;}
  for(int j=0;j<2;j++)power[j]+=n2(gain[j]*a[j][t]);
 }
 quality[0]=train/fmax(nt,1)/normal;quality[1]=test/fmax(ne,1)/normal;quality[2]=fmin(power[0],power[1])/n/normal;quality[3]=corr;
 return 0;
}
int rescue_cheap_joint(const float *iq,int n,const int32_t *starts,const double *freq,const double *shape,const uint8_t *initial,const uint8_t *fixed,uint8_t *result,double *quality){
 if(n<500||n>MAX||starts[0]<4||starts[0]>n-484||starts[1]>n-484||starts[1]<=starts[0]||starts[1]-starts[0]<16||starts[1]-starts[0]>400||starts[1]+484>n)return -1;
 for(int j=0;j<2;j++)if(!isfinite(freq[j])||fabs(freq[j])>120000||fixed[j]>1)return -1;
 for(int j=0;j<224;j++)if(initial[j]>1)return -1;
 double complex z[MAX],rot[2][MAX],a[2][MAX],h[9],pulse[24],gain[3],res[MAX];uint8_t bits[224];memcpy(bits,initial,224);
 for(int j=0;j<9;j++){if(!isfinite(shape[2*j])||!isfinite(shape[2*j+1]))return -1;h[j]=shape[2*j]+I*shape[2*j+1];}
 for(int value=0;value<2;value++)for(int q=-4;q<8;q++){
  int k=q+(value?3:1);double complex v=0;if(k>=0&&k<9)v+=h[k];if(k+1>=0&&k+1<9)v+=h[k+1];pulse[12*value+q+4]=v;
 }
 for(int t=0;t<n;t++){if(!isfinite(iq[2*t])||!isfinite(iq[2*t+1]))return -1;z[t]=iq[2*t]+I*(double)iq[2*t+1];}
 for(int s=0;s<2;s++){
  double w=2*PI*freq[s]/4e6;double complex step=cos(w)+I*sin(w),osc=cos(-w*starts[s])+I*sin(-w*starts[s]);
  for(int t=0;t<n;t++){rot[s][t]=osc;osc*=step;}
 }
 for(int pass=0;pass<2;pass++){
  for(int s=0;s<2;s++)waveform(a[s],n,starts[s],bits+112*s,rot[s],h,pulse);
  if(fit(z,a,n,gain,quality))return -2;
  for(int t=0;t<n;t++)res[t]=z[t]-gain[2]-gain[0]*a[0][t]-gain[1]*a[1][t];
  for(int direction=0;direction<2;direction++)for(int b=0;b<112;b++){
   int s=direction,v=1-s,j=(int)floor((starts[s]+4.0*b-starts[v])/4.0),other=j>=0&&j<112;
   int old0=bits[112*s+b],old1=other?bits[112*v+j]:0,lo=starts[s]+32+4*b-4,hi=lo+12;
   if(other){int q=starts[v]+32+4*j-4;if(q<lo)lo=q;if(q+12>hi)hi=q+12;}
   double cost[4]={0};double complex u0[2][16],u1[2][16],w0[2][16],w1[2][16];
   for(int t=lo;t<hi;t++){
    int q=t-lo;
    for(int value=0;value<2;value++){
     u0[value][q]=bitwave(t,starts[s],b,value,rot[s],pulse);u1[value][q]=other?bitwave(t,starts[v],j,value,rot[v],pulse):0;
     w0[value][q]=gain[s]*u0[value][q];w1[value][q]=other?gain[v]*u1[value][q]:0;
    }
    double complex rest=res[t]+(w0[old0][q]+w1[old1][q]);
    for(int code=0;code<4;code++)cost[code]+=n2(rest-(w0[code/2][q]+w1[code%2][q]));
   }
   int best=old0*2+old1;
   for(int code=0;code<4;code++)if((!fixed[s]||code/2==old0)&&(!other||!fixed[v]||code%2==old1)&&cost[code]<cost[best])best=code;
   bits[112*s+b]=best/2;if(other)bits[112*v+j]=best%2;
   for(int t=lo;t<hi;t++){int q=t-lo;res[t]+=gain[s]*(u0[old0][q]-u0[bits[112*s+b]][q])+(other?gain[v]*(u1[old1][q]-u1[bits[112*v+j]][q]):0);}
  }
 }
 for(int s=0;s<2;s++)waveform(a[s],n,starts[s],bits+112*s,rot[s],h,pulse);
 if(fit(z,a,n,gain,quality))return -2;
 memcpy(result,bits,224);
 return quality[0]<.65&&quality[1]<.85&&quality[2]>=.02&&quality[3]<.98?1:0;
}

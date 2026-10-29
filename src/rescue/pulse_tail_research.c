/* Offline pulse-tail retry. Reuses a carrier; no payload, CRC or grid search. */
#include <complex.h>
#include <stdint.h>
#include <math.h>
#include <string.h>
#define PI 3.14159265358979323846
static double norm2(double complex z){return creal(z)*creal(z)+cimag(z)*cimag(z);}
static int solve(double complex a[4][4],double complex b[4],double complex h[4]){
 for(int k=0;k<4;k++){
  int pivot=k;for(int j=k+1;j<4;j++)if(cabs(a[j][k])>cabs(a[pivot][k]))pivot=j;
  if(cabs(a[pivot][k])<1e-20)return -1;
  for(int j=0;j<4;j++){double complex v=a[k][j];a[k][j]=a[pivot][j];a[pivot][j]=v;}
  double complex v=b[k];b[k]=b[pivot];b[pivot]=v;
  for(int j=k+1;j<4;j++){v=a[j][k]/a[k][k];for(int t=k;t<4;t++)a[j][t]-=v*a[k][t];b[j]-=v*b[k];}
 }
 for(int k=3;k>=0;k--){h[k]=b[k];for(int j=k+1;j<4;j++)h[k]-=a[k][j]*h[j];h[k]/=a[k][k];}return 0;
}
static double delta(int n,int q){return n>=q&&n<q+2?1:(n>=q+2&&n<q+4?-1:0);}
int rescue_pulse_tail(const float *iq,int64_t total,const int64_t *starts,const double *freq,const uint8_t *initial,int n,double *logits){
 if(n<0||n>8||total<480)return -1;
 for(int k=0;k<n;k++){
  if(starts[k]<0||starts[k]+480>total||!isfinite(freq[k])||fabs(freq[k])>120000)return -1;
  double complex z[480],rotation[480],columns[480][4],residual[480];double w[480];uint8_t bits[112];
  memcpy(bits,initial+k*112,112);for(int b=0;b<112;b++)if(bits[b]>1)return -1;
  double omega=-2*PI*freq[k]/4e6;double complex step=cos(omega)+I*sin(omega),osc=1;
  for(int t=0;t<480;t++){const float *v=iq+2*(starts[k]+t);if(!isfinite(v[0])||!isfinite(v[1]))return -1;rotation[t]=osc;z[t]=(v[0]+I*(double)v[1])*osc;osc*=step;}
  for(int pass=0;pass<2;pass++){
   memset(w,0,sizeof(w));int pre[8]={0,1,4,5,14,15,18,19};for(int j=0;j<8;j++)w[pre[j]]=1;
   for(int b=0;b<112;b++){int q=32+4*b;w[q]=w[q+1]=bits[b];w[q+2]=w[q+3]=!bits[b];}
   double complex gram[4][4]={{0}},rhs[4]={0},h[4]={0};
   for(int t=0;t<480;t++){
    columns[t][0]=t+1<480?w[t+1]:0;columns[t][1]=w[t];columns[t][2]=t>0?w[t-1]:0;columns[t][3]=rotation[t];
    for(int i=0;i<4;i++){rhs[i]+=conj(columns[t][i])*z[t];for(int j=0;j<4;j++)gram[i][j]+=conj(columns[t][i])*columns[t][j];}
   }
   double trace=0;for(int i=0;i<4;i++)trace+=creal(gram[i][i]);double reg=.001*fmax(trace/4,1e-9);for(int i=0;i<4;i++)gram[i][i]+=reg;
   if(solve(gram,rhs,h))return -2;
   for(int t=0;t<480;t++){residual[t]=z[t];for(int j=0;j<4;j++)residual[t]-=columns[t][j]*h[j];}
   for(int b=0;b<112;b++){
    int q=32+4*b;double dot=0,power=0;
    for(int t=q-1;t<=q+4&&t<480;t++){
     double complex v=h[0]*delta(t+1,q)+h[1]*delta(t,q)+h[2]*delta(t-1,q);
     dot+=creal(conj(v)*residual[t]);power+=norm2(v);
    }
    logits[k*112+b]=2*dot+(bits[b]?1:-1)*power;
   }
   for(int b=0;b<112;b++)bits[b]=logits[k*112+b]>0;
  }
 }return 0;
}

/* Offline bounded soft decision-directed phase/frequency refinement.
 * No CRC/header bits are forced. No persistent loop across transmitters. */
#include <math.h>
#include <stdint.h>
#include <complex.h>
#define SF_PI 3.14159265358979323846
static const int sf_pre[8]={0,1,4,5,14,15,18,19};
static void sf_rotate(const float *z,double omega,double phase,double complex *out){
 double complex osc=cexp(-I*phase),step=cexp(-I*omega);
 for(int j=0;j<480;j++){out[j]=((double)z[2*j]+I*(double)z[2*j+1])*osc;osc*=step;}
}
int rescue_soft_feedback(const float *iq,int64_t length,const int64_t *starts,int64_t n,int iterations,float *logits,float *confidence,double *freq) {
 if(n<0||n>64||iterations<1||iterations>2)return -1;
 for(int64_t k=0;k<n;k++){
  int64_t at=starts[k];if(at<0||at>length-480)return -1;const float *z=iq+2*at;
  for(int j=0;j<960;j++)if(!isfinite(z[j]))return -1;
  double best=-1,omega=0,phase=0;
  for(int f=0;f<41;f++){
   double w=2*SF_PI*(-100000+5000*f)/4000000.;double complex a=0;
   for(int j=0;j<8;j++){int p=sf_pre[j];a+=((double)z[2*p]+I*(double)z[2*p+1])*cexp(-I*w*p);}
   double power=creal(a*conj(a));if(power>best){best=power;omega=w;phase=carg(a);}
  }
  double complex rotated[480];
  for(int iteration=0;iteration<iterations;iteration++){
   sf_rotate(z,omega,phase,rotated);
   double noise=0;for(int j=0;j<32;j++){int on=0;for(int p=0;p<8;p++)if(j==sf_pre[p])on=1;if(!on)noise+=creal(rotated[j]*conj(rotated[j]));}noise=fmax(noise/24,1e-8);
   double sw=0,sx=0,sy=0,sxx=0,sxy=0;
   for(int b=0;b<112;b++){
    int q=32+4*b;double complex left=(rotated[q]+rotated[q+1])*.5,right=(rotated[q+2]+rotated[q+3])*.5;
    double dl=creal(left),dr=creal(right),score=(dl-dr)/sqrt(noise);
    double probability=1/(1+exp(-fmax(-20,fmin(20,score))));
    /* Soft weights, no target bits, prior address, or future packets. */
    for(int side=0;side<2;side++){
     double p=side?1-probability:probability;double complex a=side?right:left;
     double angle=carg(a),weight=p*p*creal(a*conj(a));double x=q+2*side+.5;
     if(p<.7||fabs(angle)>.8)continue;
     sw+=weight;sx+=weight*x;sy+=weight*angle;sxx+=weight*x*x;sxy+=weight*x*angle;
    }
   }
   double denom=sw*sxx-sx*sx;
   if(sw<=1e-8||denom<=1e-8)break;
   double slope=(sw*sxy-sx*sy)/denom,intercept=(sy-slope*sx)/sw;
   if(fabs(slope)*4000000/(2*SF_PI)>10000||fabs(intercept)>.8)break;
   omega+=slope;phase+=intercept;
  }
  sf_rotate(z,omega,phase,rotated);freq[k]=omega*4000000/(2*SF_PI);
  for(int b=0;b<112;b++){
   int q=32+4*b;double l=creal(rotated[q]+rotated[q+1]),r=creal(rotated[q+2]+rotated[q+3]);double d=l-r;
   logits[k*112+b]=(float)d;confidence[k*112+b]=(float)fmin(1.,fabs(d)/(fabs(l)+fabs(r)+1e-9));
  }
 }
 return 0;
}

/* Separate offline coherent research kernel. No sockets, SDR access or linkage
 * into readsb. No fast-math. Tables become immutable after explicit init. */
#include <stdint.h>
#include <stdlib.h>
#include <math.h>
#include <complex.h>
#include <string.h>
#define PI 3.14159265358979323846264338327950288
#define RATE 4000000.0
typedef struct { uint32_t key; int a,b; } Pattern;
static Pattern patterns[6328];
static double complex carriers[41][8];
static const int preamble[8]={0,1,4,5,14,15,18,19};
static int compare_double(const void *a,const void *b) {
    double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y);
}
static int compare_pattern(const void *a,const void *b) {
    uint32_t x=((const Pattern *)a)->key,y=((const Pattern *)b)->key;return (x>y)-(x<y);
}
#include "coherent_sort.h"
static uint32_t crc(const uint8_t *row) {
    uint32_t c=0;
    for(int b=0;b<112;b++) {
        int top=((c>>23)&1)^((row[b/8]>>(7-b%8))&1);
        c=(c<<1)&0xffffff;if(top)c^=0xfff409;
    }
    return c;
}
int rescue_coherent_init(void) {
    uint32_t bit[112];uint8_t row[14];int n=0;
    for(int b=0;b<112;b++) {memset(row,0,14);row[b/8]=1<<(7-b%8);bit[b]=crc(row);}
    for(int a=0;a<112;a++) {
        patterns[n++]=(Pattern){bit[a],a,-1};
        for(int b=a+1;b<112;b++)patterns[n++]=(Pattern){bit[a]^bit[b],a,b};
    }
    qsort(patterns,6328,sizeof(Pattern),compare_pattern);
    for(int j=1;j<6328;j++)if(patterns[j].key==patterns[j-1].key)return -1;
    for(int f=0;f<41;f++)for(int j=0;j<8;j++) {
        double a=-2*PI*(-100000+5000*f)*preamble[j]/RATE;
        carriers[f][j]=cos(a)+I*sin(a);
    }
    return 0;
}
static double quantile(double *values,int n,double fraction) {
    coherent_sort(values,n);
    double index=(n-1)*fraction;int lo=(int)index,hi=(int)ceil(index);
    return values[lo]+(values[hi]-values[lo])*(index-lo);
}
/* Weighted centered least squares, equivalent to polyfit degree 1 with w^2.
 * Sample coordinates avoid the poorly scaled [seconds,1] design matrix. */
static int line_fit(const double *x,const double *y,const double *w,const int *use,
                    int n,double *slope,double *intercept) {
    double sw=0,sx=0,sy=0;
    for(int k=0;k<n;k++)if(!use||use[k]) {double q=w[k]*w[k];sw+=q;sx+=q*x[k];sy+=q*y[k];}
    if(sw<=0)return -1;
    double mx=sx/sw,my=sy/sw,num=0,den=0;
    for(int k=0;k<n;k++)if(!use||use[k]) {
        double q=w[k]*w[k],dx=x[k]-mx;num+=q*dx*(y[k]-my);den+=q*dx*dx;
    }
    if(den<=1e-30)return -1;
    *slope=num/den;*intercept=my-(*slope)*mx;return 0;
}
static int decode(const double *logits,const double *confidence,uint8_t *row,int8_t *flips) {
    memset(row,0,14);flips[0]=flips[1]=-1;
    for(int b=0;b<112;b++)if(logits[b]>0)row[b/8]|=1<<(7-b%8);
    if((row[0]>>3)!=17)return 0;
    uint32_t syndrome=crc(row);if(!syndrome)return 1;
    int lo=0,hi=6328;
    while(lo<hi) {int m=lo+(hi-lo)/2;if(patterns[m].key<syndrome)lo=m+1;else hi=m;}
    if(lo==6328||patterns[lo].key!=syndrome)return 0;
    int least[6]={-1,-1,-1,-1,-1,-1};
    for(int b=32;b<112;b++)for(int j=0;j<6;j++) {
        if(least[j]<0||confidence[b]<confidence[least[j]]) {
            for(int q=5;q>j;q--)least[q]=least[q-1];least[j]=b;break;
        }
    }
    int bits[2]={patterns[lo].a,patterns[lo].b};
    for(int i=0;i<2;i++)if(bits[i]>=0) {
        int allowed=0;
        for(int j=0;j<6;j++)if(least[j]==bits[i]&&confidence[bits[i]]<=.35)allowed=1;
        if(!allowed)return 0;
    }
    for(int i=0;i<2;i++)if(bits[i]>=0){row[bits[i]/8]^=1<<(7-bits[i]%8);flips[i]=bits[i];}
    return 1;
}

int rescue_coherent(const float *iq,int64_t total,const int64_t *starts,int64_t n,
    double *logits,double *confidence,uint8_t *tracked,double *frequency,int32_t *inliers,
    uint8_t *rows,int8_t *flips,uint8_t *valid) {
    if(n<0||n>4096)return -1;
    for(int64_t k=0;k<n;k++) {
        int64_t at=starts[k];if(at<0||at+480>total)return -1;
        const float *z=iq+2*at;double *l=logits+112*k,*c=confidence+112*k;
        float p[480];int positions[112];double magnitude[112],sorted[112];
        for(int q=0;q<480;q++){float a=hypotf(z[2*q],z[2*q+1]);p[q]=a*a;}
        for(int b=0;b<112;b++) {
            int q=32+4*b;float left=p[q]+p[q+1],right=p[q+2]+p[q+3];
            l[b]=left-right;c[b]=fabsf(left-right)/(left+right+1.e-9f);
            positions[b]=q+(l[b]>0?0:2);
        }
        /* Experimental lag-14 preamble estimate. The ordinary 41-bin search
         * remains the default build; this is built only in an isolated library. */
#ifdef RESCUE_COARSE_PAIR
        double complex pair=0;
        for(int j=0;j<4;j++) {
            int a=preamble[j],b=preamble[j+4];
            double complex early=z[2*a]+I*(double)z[2*a+1];
            double complex late=z[2*b]+I*(double)z[2*b+1];
            pair+=late*conj(early);
        }
        double coarse=carg(pair)*RATE/(2*PI*14);
#else
        int selected=0;double best=-1;
        for(int f=0;f<41;f++) {
            double complex a=0;
            for(int j=0;j<8;j++) {int q=preamble[j];a+=(z[2*q]+I*(double)z[2*q+1])*carriers[f][j];}
            double power=creal(a)*creal(a)+cimag(a)*cimag(a);
            if(power>best){best=power;selected=f;}
        }
        double coarse=-100000+selected*5000;
#endif
        double omega=2*PI*coarse/RATE;
        double complex rotated[480],oscillator=1,step=cos(omega)-I*sin(omega);
        for(int q=0;q<480;q++){rotated[q]=(z[2*q]+I*(double)z[2*q+1])*oscillator;oscillator*=step;}
        for(int b=0;b<112;b++){int q=positions[b];magnitude[b]=cabs((rotated[q]+rotated[q+1])*.5);sorted[b]=magnitude[b];}
        double cutoff=quantile(sorted,112,.35),x[112],y[112],weights[112],mw[112];
        int good[112],count=0;double previous=0,unwrapped=0;
        for(int b=0;b<112;b++)if(c[b]>=.5&&magnitude[b]>=cutoff) {
            int q=positions[b];double angle=carg(rotated[q]+rotated[q+1]);
            if(count){double delta=angle-previous;if(delta>PI)delta-=2*PI;else if(delta<-PI)delta+=2*PI;unwrapped+=delta;}
            else unwrapped=angle;
            previous=angle;x[count]=q+.5;y[count]=unwrapped;
            good[count]=q;weights[count]=mw[count]=magnitude[b];count++;
        }
        tracked[k]=0;frequency[k]=NAN;inliers[k]=0;
#ifdef RESCUE_ROBUST_FIT
        valid[k]=0;memset(rows+14*k,0,14);flips[2*k]=flips[2*k+1]=-1;
#endif
        if(count>=24) {
            double cap=2*quantile(mw,count,.5),slope=0,intercept=0;
            for(int j=0;j<count;j++)weights[j]=fmin(weights[j],cap);
            if(!line_fit(x,y,weights,NULL,count,&slope,&intercept)) {
                int use[112],kept=0;
                for(int j=0;j<count;j++){double residual=y[j]-slope*x[j]-intercept;use[j]=fabs(atan2(sin(residual),cos(residual)))<.8;kept+=use[j];}
#ifdef RESCUE_ROBUST_FIT
                /* Two bounded rejection/refit rounds; the final phase fit and
                 * matched template use exactly the same retained pulses. */
                int fit_ok=kept>=24;
                for(int pass=0;pass<2 && fit_ok;pass++) {
                    if(line_fit(x,y,weights,use,count,&slope,&intercept)) {fit_ok=0;break;}
                    kept=0;
                    for(int j=0;j<count;j++) {
                        double r=y[j]-slope*x[j]-intercept;
                        use[j]=use[j] && fabs(atan2(sin(r),cos(r)))<.8;
                        kept+=use[j];
                    }
                    if(kept<24)fit_ok=0;
                }
                if(!fit_ok || line_fit(x,y,weights,use,count,&slope,&intercept))continue;
#else
                if(kept>=24)line_fit(x,y,weights,use,count,&slope,&intercept);
#endif
                if(isfinite(slope)&&isfinite(intercept)&&fabs(slope*RATE/(2*PI))<=30000) {
                    tracked[k]=1;frequency[k]=coarse+slope*RATE/(2*PI);inliers[k]=kept;
                    omega+=slope;step=cos(omega)-I*sin(omega);oscillator=cos(intercept)-I*sin(intercept);
                    for(int q=0;q<480;q++){rotated[q]=(z[2*q]+I*(double)z[2*q+1])*oscillator;oscillator*=step;}
                    double complex shape[2]={0,0};
                    for(int j=0;j<count;j++) {
#ifdef RESCUE_ROBUST_FIT
                        if(!use[j])continue;
#endif
                        shape[0]+=rotated[good[j]];shape[1]+=rotated[good[j]+1];
                    }
#ifdef RESCUE_ROBUST_FIT
                    shape[0]=conj(shape[0]/kept);shape[1]=conj(shape[1]/kept);
#else
                    shape[0]=conj(shape[0]/count);shape[1]=conj(shape[1]/count);
#endif
                    for(int b=0;b<112;b++) {
                        int q=32+4*b;
                        double left=creal(rotated[q]*shape[0]+rotated[q+1]*shape[1]);
                        double right=creal(rotated[q+2]*shape[0]+rotated[q+3]*shape[1]);
                        l[b]=left-right;c[b]=fabs(l[b])/(fabs(left)+fabs(right)+1.e-9);
                    }
                }
            }
        }
#ifdef RESCUE_ROBUST_FIT
        /* This branch is a coherent-only retry, never an energy fallback. */
        if(!tracked[k])continue;
#endif
        valid[k]=decode(l,c,rows+14*k,flips+2*k);
    }
    return 0;
}

typedef struct {double score;int64_t position;} Peak;
static int by_score(const void *a,const void *b) {
    const Peak *x=a,*y=b;
    if(x->score!=y->score)return x->score>y->score?-1:1;
    return (x->position<y->position)-(x->position>y->position);
}
static int by_position(const void *a,const void *b) {
    int64_t x=((const Peak *)a)->position,y=((const Peak *)b)->position;return (x>y)-(x<y);
}
/* Same local-max/plateau and distance=3 rules as scipy.find_peaks. Equal-score
 * distance ties are deterministic rightmost-first; equivalence is audited. */
int64_t rescue_coherent_peaks(const double *score,int64_t n,int64_t core,int64_t total,
                              double threshold,int64_t *out) {
    if(n<3||core<0||n>10000000)return -1;
    Peak *peaks=malloc(sizeof(Peak)*n);uint8_t *masked=calloc(n,1);
    if(!peaks||!masked){free(peaks);free(masked);return -1;}
    int64_t count=0;
    for(int64_t j=1;j<n-1;j++)if(score[j]>=threshold&&score[j]>score[j-1]) {
        int64_t end=j;while(end+1<n&&score[end+1]==score[j])end++;
        if(end<n-1&&score[end]>score[end+1])peaks[count++]=(Peak){score[j],(j+end)/2};
        j=end;
    }
    qsort(peaks,count,sizeof(Peak),by_score);int64_t keep=0;
    for(int64_t j=0;j<count;j++) {
        int64_t pos=peaks[j].position;if(masked[pos])continue;
        for(int t=-2;t<=2;t++)if(pos+t>=0&&pos+t<n)masked[pos+t]=1;
        peaks[keep++]=peaks[j];
    }
    qsort(peaks,keep,sizeof(Peak),by_position);int64_t output=0;
    for(int64_t j=0;j<keep;j++) {int64_t pos=peaks[j].position;if(pos<core&&pos+480<=total)out[output++]=pos;}
    free(peaks);free(masked);return output;
}

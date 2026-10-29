/* Offline experiment kernel. No sockets, aircraft identity or known payload input.
 * Reuses ONLY bounded DF17 CRC/weak-bit admission and tables from frozen kernel.
 */
#include "coherent_kernel.c"
static double complex sf_rot(double complex z,double w,int n){return z*(cos(w*n)-I*sin(w*n));}
static double sf_noise(const float *z){double a[112];for(int b=0;b<112;b++){int q=32+4*b;double e=0,f=0;for(int t=0;t<2;t++){double complex x=z[2*(q+t)]+I*z[2*(q+t)+1],y=z[2*(q+2+t)]+I*z[2*(q+2+t)+1];e+=creal(x*conj(x));f+=creal(y*conj(y));}a[b]=fmin(e,f)*.5;}return fmax(quantile(a,112,.5),1.e-8);}
static double sf_seed(const float *z,double supplied){if(isfinite(supplied))return supplied;double best=-1,freq=0;for(int f=0;f<41;f++){double complex a=0;for(int j=0;j<8;j++){int q=preamble[j];a+=(z[2*q]+I*(double)z[2*q+1])*carriers[f][j];}double p=creal(a*conj(a));if(p>best){best=p;freq=-100000+5000*f;}}return freq;}
static double complex sf_gain(const float *z,double w,const double *prob){double complex a=0;for(int n=0;n<480;n++){double p=0;if(n<32){for(int j=0;j<8;j++)if(n==preamble[j])p=1;}else{int b=(n-32)/4,t=(n-32)%4;p=t<2?prob[b]:1-prob[b];}a+=p*sf_rot(z[2*n]+I*(double)z[2*n+1],w,n-240);}return a/232.;}
static void sf_em(const float *z,double seed,int iterations,double *l,double *c,double *freq){double p[112];double w=seed*2*PI/RATE,noise=sf_noise(z);for(int b=0;b<112;b++)p[b]=l[b]>0?.95:.05;double complex g=sf_gain(z,w,p);
 for(int it=0;it<iterations;it++){
  for(int b=0;b<112;b++){double complex d=0;for(int t=0;t<2;t++){int q=32+4*b+t;d+=sf_rot(z[2*q]+I*(double)z[2*q+1],w,q-240)-sf_rot(z[2*(q+2)]+I*(double)z[2*(q+2)+1],w,q+2-240);}double v=2*creal(conj(g)*d)/noise;v=fmax(-30,fmin(30,v));p[b]=1/(1+exp(-v));}
  double best=-1,bw=w;double complex bg=g;double step=(4000./(1<<it))*2*PI/RATE;
  for(int k=-2;k<=2;k++){double cw=w+k*step;double complex cg=sf_gain(z,cw,p);double score=creal(cg*conj(cg));if(score>best){best=score;bw=cw;bg=cg;}}
  w=bw;g=bg;
 }
 for(int b=0;b<112;b++){double left=0,right=0;for(int t=0;t<2;t++){int q=32+4*b+t;left+=creal(conj(g)*sf_rot(z[2*q]+I*(double)z[2*q+1],w,q-240));q+=2;right+=creal(conj(g)*sf_rot(z[2*q]+I*(double)z[2*q+1],w,q-240));}l[b]=left-right;c[b]=fabs(l[b])/(fabs(left)+fabs(right)+1.e-9);}
 *freq=w*RATE/(2*PI);
}
static double sf_pulse(int n,int bit,int state,int current){if(n<0||n>=480)return 0;if(n<32){for(int j=0;j<8;j++)if(n==preamble[j])return 1;return 0;}int b=(n-32)/4,t=(n-32)%4,v=0;if(b==bit)v=current;else if(b==bit-1)v=state&1;else if(b==bit-2)v=(state>>1)&1;return t<2?v:1-v;}
static void sf_seq(const float *window,double seed,const double *hr,const double *hi,double *l,double *c){const float *z=window+16;double w=seed*2*PI/RATE;double complex h[9],obs[114][4],templ[114][4][2][4];for(int k=0;k<9;k++)h[k]=hr[k]+I*hi[k];double complex g=0;double den=0;
 /* Gain uses known preamble only; no decoded or stock payload steers the fit. */
 for(int n=4;n<28;n++){double complex p=0;for(int k=0;k<9;k++){int j=n-k;if(j>=0&&j<32)for(int t=0;t<8;t++)if(j==preamble[t])p+=h[k];}int q=8+n-4;double complex y=sf_rot(window[2*q]+I*(double)window[2*q+1],w,n-4-240);g+=conj(p)*y;den+=creal(p*conj(p));}g/=fmax(den,1.e-12);
 for(int b=0;b<114;b++)for(int t=0;t<4;t++){int n=32+4*b+t,q=8+n-4;obs[b][t]=sf_rot(window[2*q]+I*(double)window[2*q+1],w,n-4-240);for(int s=0;s<4;s++)for(int v=0;v<2;v++){double complex p=0;for(int k=0;k<9;k++)p+=h[k]*sf_pulse(n-k,b,s,v);templ[b][s][v][t]=g*p;}}
 double cost[114][4][2],a[115][4],back[115][4];int trace[114][4];
 for(int s=0;s<4;s++){a[0][s]=s?1.e100:0;back[114][s]=0;}
 for(int b=0;b<114;b++){
  for(int s=0;s<4;s++)a[b+1][s]=1.e100;
  for(int s=0;s<4;s++)for(int v=0;v<2;v++){double e=0;for(int t=0;t<4;t++){double complex d=obs[b][t]-templ[b][s][v][t];e+=creal(d*conj(d));}if(b>=112&&v)e=1.e100;cost[b][s][v]=e;int next=((s&1)<<1)|v;if(a[b][s]+e<a[b+1][next]){a[b+1][next]=a[b][s]+e;trace[b][next]=s;}}
 }
 for(int b=113;b>=0;b--)for(int s=0;s<4;s++)back[b][s]=fmin(cost[b][s][0]+back[b+1][(s&1)<<1],cost[b][s][1]+back[b+1][((s&1)<<1)|1]);
 int state=0;for(int s=1;s<4;s++)if(a[114][s]<a[114][state])state=s;int bits[114];for(int b=113;b>=0;b--){bits[b]=state&1;state=trace[b][state];}
 double noise=sf_noise(z);
 for(int b=0;b<112;b++){double best[2]={1.e100,1.e100};for(int s=0;s<4;s++)for(int v=0;v<2;v++){int next=((s&1)<<1)|v;double x=a[b][s]+cost[b][s][v]+back[b+1][next];if(x<best[v])best[v]=x;}double strength=fabs(best[0]-best[1]);l[b]=(bits[b]?1:-1)*fmax(strength,1.e-20);c[b]=1-exp(-strength/fmax(4*noise,1.e-12));}
}
int rescue_science(const float *windows,int64_t n,const double *seeds,const double *initial_l,const double *initial_c,const double *hr,const double *hi,int method,int iterations,double *out_l,double *out_c,uint8_t *rows,int8_t *flips,uint8_t *valid,double *frequency){
 if(n<0||n>4096||method<0||method>2||iterations<1||iterations>4)return -1;
 for(int64_t k=0;k<n;k++){const float *window=windows+k*992,*z=window+16;double *l=out_l+k*112,*c=out_c+k*112;for(int b=0;b<112;b++){l[b]=initial_l[k*112+b];c[b]=initial_c[k*112+b];}double freq=sf_seed(z,seeds[k]);if(method!=1)sf_em(z,freq,iterations,l,c,&freq);if(method!=0)sf_seq(window,freq,hr,hi,l,c);frequency[k]=freq;valid[k]=decode(l,c,rows+k*14,flips+k*2);}
 return 0;
}

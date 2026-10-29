/* Optional compact export. Frozen full diagnostic API remains intact. */
#define rescue_coherent rescue_coherent_full_reference
#include "coherent_kernel.c"
#undef rescue_coherent
int rescue_coherent_compact(const float *iq,int64_t total,const int64_t *starts,int64_t n,uint8_t *rows,int8_t *flips,uint8_t *valid) {
    if(n<0||n>4096)return -1;
    for(int64_t k=0;k<n;k++) {
        int64_t at=starts[k];if(at<0||total<480||at>total-480)return -1;
        const float *z=iq+2*at;double l[112],c[112];
        float p[480];int positions[112];double magnitude[112],sorted[112];
        for(int q=0;q<480;q++){float a=hypotf(z[2*q],z[2*q+1]);p[q]=a*a;}
        for(int b=0;b<112;b++) {
            int q=32+4*b;float left=p[q]+p[q+1],right=p[q+2]+p[q+3];
            l[b]=left-right;c[b]=fabsf(left-right)/(left+right+1.e-9f);
            positions[b]=q+(l[b]>0?0:2);
        }
        int selected=0;double best=-1;
        for(int f=0;f<41;f++) {
            double complex a=0;
            for(int j=0;j<8;j++) {int q=preamble[j];a+=(z[2*q]+I*(double)z[2*q+1])*carriers[f][j];}
            double power=creal(a)*creal(a)+cimag(a)*cimag(a);
            if(power>best){best=power;selected=f;}
        }
        double coarse=-100000+selected*5000,omega=2*PI*coarse/RATE;
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

        if(count>=24) {
            double cap=2*quantile(mw,count,.5),slope=0,intercept=0;
            for(int j=0;j<count;j++)weights[j]=fmin(weights[j],cap);
            if(!line_fit(x,y,weights,NULL,count,&slope,&intercept)) {
                int use[112],kept=0;
                for(int j=0;j<count;j++){double residual=y[j]-slope*x[j]-intercept;use[j]=fabs(atan2(sin(residual),cos(residual)))<.8;kept+=use[j];}
                if(kept>=24)line_fit(x,y,weights,use,count,&slope,&intercept);
                if(isfinite(slope)&&isfinite(intercept)&&fabs(slope*RATE/(2*PI))<=30000) {

                    omega+=slope;step=cos(omega)-I*sin(omega);oscillator=cos(intercept)-I*sin(intercept);
                    for(int q=0;q<480;q++){rotated[q]=(z[2*q]+I*(double)z[2*q+1])*oscillator;oscillator*=step;}
                    double complex shape[2]={0,0};
                    for(int j=0;j<count;j++){shape[0]+=rotated[good[j]];shape[1]+=rotated[good[j]+1];}
                    shape[0]=conj(shape[0]/count);shape[1]=conj(shape[1]/count);
                    for(int b=0;b<112;b++) {
                        int q=32+4*b;
                        double left=creal(rotated[q]*shape[0]+rotated[q+1]*shape[1]);
                        double right=creal(rotated[q+2]*shape[0]+rotated[q+3]*shape[1]);
                        l[b]=left-right;c[b]=fabs(l[b])/(fabs(left)+fabs(right)+1.e-9);
                    }
                }
            }
        }
        valid[k]=decode(l,c,rows+14*k,flips+2*k);
    }
    return 0;
}

/* Frozen eight-tap PPM discriminant. No CRC/header/address modification. */
#include <math.h>
#include <stdint.h>
#include <stddef.h>
int rescue_pulse_discriminant(const float *power,int64_t length,const int64_t *starts,int64_t count,const double *weights,double bias,float *logits,float *confidence) {
    static const int pre[8]={0,1,4,5,14,15,18,19};
    if(length<482 || count<0 || !isfinite(bias)) return -1;
    for(int k=0;k<8;k++) if(!isfinite(weights[k])) return -1;
    for(int64_t j=0;j<count;j++) {
        int64_t at=starts[j];if(at<0 || at>length-482) return -1;
        double scale=0;for(int k=0;k<8;k++) {double p=power[at+pre[k]];if(!isfinite(p) || p<0) return -1;scale+=p;}scale=fmax(scale/8,1e-6);
        for(int bit=0;bit<112;bit++) {
            double sum=0,den=0;
            for(int k=0;k<8;k++) {double p=power[at+32+4*bit+k-2];if(!isfinite(p) || p<0) return -1;sum+=weights[k]*p;den+=fabs(weights[k])*p;}
            double value=sum/scale+bias;logits[j*112+bit]=(float)value;
            confidence[j*112+bit]=(float)fmin(1.,fabs(value)/(den/scale+fabs(bias)+1e-9));
        }
    }
    return 0;
}

/* Offline bank: read/validate each bit neighborhood and preamble scale once.
 * Each model retains the scalar kernel's arithmetic order and confidence. */
int rescue_pulse_bank(const float *power,int64_t length,const int64_t *starts,int64_t count,const double *weights,const double *bias,int64_t models,float *logits,float *confidence) {
    static const int pre[8]={0,1,4,5,14,15,18,19};
    if(length<482 || count<0 || models<1 || models>8) return -1;
    for(int64_t m=0;m<models;m++) {
        if(!isfinite(bias[m])) return -1;
        for(int k=0;k<8;k++) if(!isfinite(weights[m*8+k])) return -1;
    }
    for(int64_t j=0;j<count;j++) {
        int64_t at=starts[j];if(at<0 || at>length-482) return -1;
        double scale=0;
        for(int k=0;k<8;k++) {double v=power[at+pre[k]];if(!isfinite(v)||v<0)return -1;scale+=v;}
        scale=fmax(scale/8,1e-6);
        for(int bit=0;bit<112;bit++) {
            double values[8];
            for(int k=0;k<8;k++){values[k]=power[at+32+4*bit+k-2];if(!isfinite(values[k])||values[k]<0)return -1;}
            for(int64_t m=0;m<models;m++) {
                double sum=0,den=0;
                for(int k=0;k<8;k++){double w=weights[m*8+k];sum+=w*values[k];den+=fabs(w)*values[k];}
                double value=sum/scale+bias[m];int64_t index=(j*models+m)*112+bit;
                logits[index]=(float)value;confidence[index]=(float)fmin(1.,fabs(value)/(den/scale+fabs(bias[m])+1e-9));
            }
        }
    }
    return 0;
}

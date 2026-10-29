/* Offline research only. No receiver linkage, allocation, I/O or global state. */
#include <stdint.h>
#include <stddef.h>
int rescue_variable_windows(const float *restrict iq,int64_t total,const int64_t *starts,
                            const int64_t *integer,const float *weights,int64_t n,float *restrict out) {
    for(int64_t k=0;k<n;k++) {
        int64_t at=starts[k]+integer[k];
        if(at<3 || at+483>=total)return -1;
        float *restrict dest=out+k*960;
        for(int q=0;q<960;q++)dest[q]=0;
        for(int j=0;j<8;j++) {
            const float *restrict src=iq+2*(at+j-3);float weight=weights[k*8+j];
            for(int q=0;q<960;q++)dest[q]+=src[q]*weight;
        }
    }
    return 0;
}

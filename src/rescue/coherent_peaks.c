/* SPDX-License-Identifier: GPL-3.0-or-later
 * Unchanged peak-selector tail extracted from coherent_kernel.c.
 * Rust replaces the window decoder; this ABI helper remains C. */
#include <stdint.h>
#include <stdlib.h>
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

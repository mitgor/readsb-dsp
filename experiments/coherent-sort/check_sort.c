#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int compare_double(const void *a,const void *b){double x=*(const double*)a,y=*(const double*)b;return(x>y)-(x<y);}
#include "coherent_sort.h"
static uint64_t state=20261029;
static uint32_t random32(void){state^=state<<13;state^=state>>7;state^=state<<17;return (uint32_t)state;}
int main(void){
    for(int trial=0;trial<200000;trial++){
        double a[114],b[112];int n=trial%113;a[0]=1234567;a[n+1]=7654321;
        for(int j=0;j<n;j++) {
            double value=(int32_t)random32()/65536.0;
            switch((trial/113)%7){case 0:value=j;break;case 1:value=-j;break;case 2:value=1;break;case 3:value=(int)(value*65536)%5;break;case 4:value=j<n/2?j:n-j;break;}
            a[j+1]=b[j]=value;
        }
        if(n>0 && trial%101==0)a[1]=b[0]=NAN;
        if(n>1 && trial%103==0)a[2]=b[1]=INFINITY;
        qsort(b,n,sizeof(double),compare_double);coherent_sort(a+1,n);
        assert(a[0]==1234567 && a[n+1]==7654321);
        for(int j=0;j<n;j++)assert((isnan(a[j+1])&&isnan(b[j]))||a[j+1]==b[j]);
    }
    puts("200000 sort cases pass, n=0..112, duplicates, ordered, reverse, adversarial and nonfinite fallback");
}

/* SPDX-License-Identifier: Apache-2.0
 * Typed C adaptation of Goose v2026.3 stdlib/std.goose sort, by the Goose
 * contributors (https://github.com/aardappel/goose, commit acc6310a83df7a3).
 * Modified for bounded coherent double quantiles (n <= 112), with a libc
 * fallback for nonfinite input and optional reference-sort build.
 * Apache-2.0 license: docs/licenses/GOOSE-APACHE-2.0.txt.
 * This header does not depend on the Goose compiler or its runtime.
 */
#ifndef RESCUE_COHERENT_SORT_H
#define RESCUE_COHERENT_SORT_H
static void coherent_swap(double *a,int i,int j){double t=a[i];a[i]=a[j];a[j]=t;}
static void coherent_insertion(double *a,int n){
    for(int i=1;i<n;i++){
        double x=a[i];int j=i;
        while(j>0 && x<a[j-1]){a[j]=a[j-1];j--;}
        a[j]=x;
    }
}
static void coherent_sift(double *a,int n,int root){
    while(2*root+1<n){
        int child=2*root+1;
        if(child+1<n && a[child]<a[child+1])child++;
        if(!(a[root]<a[child]))break;
        coherent_swap(a,root,child);root=child;
    }
}
static void coherent_heap(double *a,int n){
    for(int i=n/2;i>0;)coherent_sift(a,n,--i);
    for(int end=n;end>1;){--end;coherent_swap(a,0,end);coherent_sift(a,end,0);}
}
static int coherent_median3(const double *a,int i,int j,int k){
    int x=a[i]<a[j];
    if(x!=(a[i]<a[k]))return i;
    if((a[j]<a[k])!=x)return k;
    return j;
}
static int coherent_partition(double *a,int n,int equal){
    double pivot=a[0];int lt=1;
    for(int i=1;i<n;i++){
        double x=a[i];a[i]=a[lt];a[lt]=x;
        lt+=equal?!(pivot<x):x<pivot;
    }
    return lt-1;
}
static void coherent_sort_finite(double *a,int n){
    if(n<=10){coherent_insertion(a,n);return;}
    int run=2;
    if(a[1]<a[0]){
        while(run<n && a[run]<a[run-1])run++;
        for(int i=0;i<run/2;i++)coherent_swap(a,i,run-1-i);
    } else while(run<n && !(a[run]<a[run-1]))run++;
    if(run==n)return;
    int limit=0;for(int x=n;x>1;x>>=1)limit+=2;
    /* At most floor(log2(112))+1 deferred ranges, three ints each. */
    int stack[32],top=0,lo=0,hi=n;
    for(;;){
        double *v=a+lo;int size=hi-lo;
        if(size>10 && limit>0){
            limit--;int eighth=size/8;
            coherent_swap(v,0,coherent_median3(v,0,4*eighth,7*eighth));
            if(lo>0 && !(a[lo-1]<v[0])){
                int m=coherent_partition(v,size,1);coherent_swap(v,0,m);lo+=m+1;continue;
            }
            int m=coherent_partition(v,size,0);coherent_swap(v,0,m);
            if(m<size-1-m){
                stack[top++]=lo+m+1;stack[top++]=hi;stack[top++]=limit;hi=lo+m;
            } else {
                stack[top++]=lo;stack[top++]=lo+m;stack[top++]=limit;lo+=m+1;
            }
            continue;
        }
        if(size>10)coherent_heap(v,size);else coherent_insertion(v,size);
        if(!top)return;
        limit=stack[--top];hi=stack[--top];lo=stack[--top];
    }
}
static void coherent_sort(double *a,int n){
#ifdef RESCUE_REFERENCE_SORT
    qsort(a,n,sizeof(double),compare_double);
#else
    if(n>112){qsort(a,n,sizeof(double),compare_double);return;}
    for(int i=0;i<n;i++)if(!isfinite(a[i])){
        qsort(a,n,sizeof(double),compare_double);return;
    }
    coherent_sort_finite(a,n);
#endif
}
#endif

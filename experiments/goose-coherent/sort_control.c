/* CPU attribution control, not the default C baseline or a deployment. */
#include <stdlib.h>
#include "coherent.h"
static void experiment_qsort(void *p,size_t n,size_t size,int (*cmp)(const void*,const void*)) {
 if(size==sizeof(double))goose_sort((sl_f64){p,(int64_t)n});
 else qsort(p,n,size,cmp);
}
#define qsort experiment_qsort
#include "../../src/rescue/coherent_kernel.c"

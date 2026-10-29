/* Identical dlopen harness for installed and candidate libraries.
 * Resolve symbols before the shared driver's timed work. No DSP math here. */
#define main measured_main
#include "../goose-coherent/driver.c"
#undef main
#include <dlfcn.h>
static int (*init_fn)(void);
static int (*decode_fn)(const float*,int64_t,const int64_t*,int64_t,double*,double*,uint8_t*,double*,int32_t*,uint8_t*,int8_t*,uint8_t*);
int rescue_coherent_init(void){return init_fn();}
int rescue_coherent(const float *iq,int64_t total,const int64_t *starts,int64_t n,double *l,double *c,uint8_t *tracked,double *frequency,int32_t *inliers,uint8_t *rows,int8_t *flips,uint8_t *valid){return decode_fn(iq,total,starts,n,l,c,tracked,frequency,inliers,rows,flips,valid);}
int main(int argc,char **argv){
 const char *path=getenv("COHERENT_LIBRARY");if(!path)return 2;
 void *handle=dlopen(path,RTLD_NOW|RTLD_LOCAL);if(!handle){fprintf(stderr,"%s\n",dlerror());return 3;}
 *(void**)(&init_fn)=dlsym(handle,"rescue_coherent_init");*(void**)(&decode_fn)=dlsym(handle,"rescue_coherent");
 if(!init_fn||!decode_fn)return 3;return measured_main(argc,argv);
}

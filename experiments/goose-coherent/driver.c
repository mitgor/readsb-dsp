/* Identical standalone input/output/timing harness for C and Goose.
 * Binary fixture: uint64 window count then 960 float32 values/window.
 * Common harness owns I/O/buffers only. Decoder math never calls through here. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>
#include <sys/resource.h>
#include <string.h>
#ifdef __APPLE__
#include <mach/mach.h>
#endif
#if defined(GOOSE) || defined(SORT_CONTROL)
#include "coherent.h"
#endif
#ifndef GOOSE
int rescue_coherent_init(void);
int rescue_coherent(const float*,int64_t,const int64_t*,int64_t,double*,double*,uint8_t*,double*,int32_t*,uint8_t*,int8_t*,uint8_t*);
#endif
static double clock_s(clockid_t which){struct timespec t;clock_gettime(which,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static long status_kb(const char *key){
#ifdef __linux__
 FILE *f=fopen("/proc/self/status","r");char line[256];long value=0;if(!f)return 0;
 while(fgets(line,sizeof(line),f))if(!strncmp(line,key,strlen(key))){sscanf(line+strlen(key),"%ld",&value);break;}fclose(f);return value;
#else
 mach_task_basic_info_data_t info;mach_msg_type_number_t count=MACH_TASK_BASIC_INFO_COUNT;
 if(task_info(mach_task_self(),MACH_TASK_BASIC_INFO,(task_info_t)&info,&count)!=KERN_SUCCESS)return 0;
 return !strcmp(key,"VmSize:")?(long)(info.virtual_size/1024):(long)(info.resident_size/1024);
#endif
}
static void checked_write(FILE *f,const void *p,size_t size,size_t n){if(fwrite(p,size,n,f)!=n){perror("write");exit(3);}}
int main(int argc,char **argv){
 if(argc!=4){fprintf(stderr,"fixture loops output\n");return 2;}
 FILE *f=fopen(argv[1],"rb");uint64_t n=0;if(!f||fread(&n,8,1,f)!=1||n<1||n>4096)return 2;
 float *iq=malloc(n*960*sizeof(float));int64_t *starts=malloc(n*sizeof(int64_t));
 if(!iq||!starts||fread(iq,960*sizeof(float),n,f)!=n)return 2;fclose(f);for(uint64_t i=0;i<n;i++)starts[i]=480*i;
 double *l=calloc(n*112,sizeof(double)),*c=calloc(n*112,sizeof(double)),*freq=calloc(n,sizeof(double));
 uint8_t *tracked=calloc(n,1),*rows=calloc(n*14,1),*valid=calloc(n,1);int32_t *inliers=calloc(n,4);int8_t *flips=calloc(n*2,1);
 if(!l||!c||!freq||!tracked||!rows||!valid||!inliers||!flips)return 2;
 long before_kb=status_kb("VmRSS:");double init=clock_s(CLOCK_PROCESS_CPUTIME_ID);
#ifdef GOOSE
 goose_init(argc,argv);
#else
#ifdef SORT_CONTROL
 goose_init(argc,argv);
#endif
 if(rescue_coherent_init())return 3;
#endif
 init=clock_s(CLOCK_PROCESS_CPUTIME_ID)-init;long initialized_kb=status_kb("VmRSS:");
 int loops=atoi(argv[2]);if(loops<1||loops>100000)return 2;double cpu=0,wall=0;
 for(int round=-2;round<loops;round++){
  if(round==0){cpu=clock_s(CLOCK_PROCESS_CPUTIME_ID);wall=clock_s(CLOCK_MONOTONIC);}
#ifdef GOOSE
  goose_coherent((sl_f32){iq,(int64_t)(960*n)},(sl_i64){starts,n},(sl_f64){l,112*n},(sl_f64){c,112*n},(sl_u8){tracked,n},(sl_f64){freq,n},(sl_i32){inliers,n},(sl_u8){rows,14*n},(sl_i8){flips,2*n},(sl_u8){valid,n});
#else
  if(rescue_coherent(iq,480*n,starts,n,l,c,tracked,freq,inliers,rows,flips,valid))return 3;
#endif
 }
 cpu=clock_s(CLOCK_PROCESS_CPUTIME_ID)-cpu;wall=clock_s(CLOCK_MONOTONIC)-wall;
 struct rusage usage;getrusage(RUSAGE_SELF,&usage);
 uint64_t rss=(uint64_t)usage.ru_maxrss;
#ifndef __APPLE__
 rss=(uint64_t)status_kb("VmHWM:")*1024; /* exec-local mm high-water, unlike inherited ru_maxrss */
#endif
 f=fopen(argv[3],"wb");if(!f)return 3;
 checked_write(f,l,8,112*n);checked_write(f,c,8,112*n);checked_write(f,tracked,1,n);checked_write(f,freq,8,n);checked_write(f,inliers,4,n);checked_write(f,rows,1,14*n);checked_write(f,flips,1,2*n);checked_write(f,valid,1,n);fclose(f);
 uint64_t packets=0,fit=0;for(uint64_t k=0;k<n;k++){packets+=valid[k]!=0;fit+=tracked[k]!=0;}
 printf("{\"windows\":%llu,\"loops\":%d,\"cpu_seconds\":%.9f,\"wall_seconds\":%.9f,\"initialization_cpu_seconds\":%.9f,\"peak_rss_bytes\":%llu,\"rss_before_init_kb\":%ld,\"rss_after_init_kb\":%ld,\"rss_after_work_kb\":%ld,\"vm_after_work_kb\":%ld,\"valid\":%llu,\"tracked\":%llu}\n",(unsigned long long)n,loops,cpu,wall,init,(unsigned long long)rss,before_kb,initialized_kb,status_kb("VmRSS:"),status_kb("VmSize:"),(unsigned long long)packets,(unsigned long long)fit);
 return 0;
}

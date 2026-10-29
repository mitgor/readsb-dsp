/* Shared preallocated C harness, original and Rust EM: no decoder math. */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sys/resource.h>
#include <string.h>
#ifdef __APPLE__
#include <mach/mach.h>
#endif
int rescue_coherent_init(void);
int rescue_science(const float*,int64_t,const double*,const double*,const double*,const double*,const double*,int,int,double*,double*,uint8_t*,int8_t*,uint8_t*,double*);
static double clock_s(clockid_t w){struct timespec t;clock_gettime(w,&t);return t.tv_sec+1e-9*t.tv_nsec;}
static long status_kb(const char *key){
#ifdef __linux__
 FILE *f=fopen("/proc/self/status","r");char line[256];long value=0;if(!f)return 0;while(fgets(line,sizeof(line),f))if(!strncmp(line,key,strlen(key))){sscanf(line+strlen(key),"%ld",&value);break;}fclose(f);return value;
#else
 mach_task_basic_info_data_t info;mach_msg_type_number_t count=MACH_TASK_BASIC_INFO_COUNT;if(task_info(mach_task_self(),MACH_TASK_BASIC_INFO,(task_info_t)&info,&count)!=KERN_SUCCESS)return 0;return !strcmp(key,"VmSize:")?info.virtual_size/1024:info.resident_size/1024;
#endif
}
static void wr(FILE*f,const void*p,size_t size,size_t n){if(fwrite(p,size,n,f)!=n)exit(3);}
int main(int argc,char**argv){
 if(argc!=5)return 2;int loops=atoi(argv[2]),iterations=atoi(argv[3]);if(loops<1||loops>100000||iterations<1||iterations>4)return 2;
 FILE*f=fopen(argv[1],"rb");uint64_t n;if(!f||fread(&n,8,1,f)!=1||n<32||n>4096)return 2;
 float*iq=malloc(n*992*4);double*seed=malloc(n*8),*il=malloc(n*112*8),*ic=malloc(n*112*8);
 if(!iq||!seed||!il||!ic)return 2;if(fread(iq,992*4,n,f)!=n||fread(seed,8,n,f)!=n||fread(il,112*8,n,f)!=n||fread(ic,112*8,n,f)!=n)return 2;fclose(f);
 double*l=calloc(n*112,8),*c=calloc(n*112,8),*freq=calloc(n,8);uint8_t*rows=calloc(n*14,1),*valid=calloc(n,1);int8_t*flips=calloc(n*2,1);double h[9]={1,0,0,0,0,0,0,0,0},hi[9]={0};
 if(!l||!c||!freq||!rows||!valid||!flips)return 2;double init=clock_s(CLOCK_PROCESS_CPUTIME_ID);if(rescue_coherent_init())return 3;init=clock_s(CLOCK_PROCESS_CPUTIME_ID)-init;
 double cpu=0,wall=0;
 for(int r=-2;r<loops;r++){
  if(r==0){cpu=clock_s(CLOCK_PROCESS_CPUTIME_ID);wall=clock_s(CLOCK_MONOTONIC);}
  if(rescue_science(iq,n,seed,il,ic,h,hi,0,iterations,l,c,rows,flips,valid,freq))return 3;
 }
 cpu=clock_s(CLOCK_PROCESS_CPUTIME_ID)-cpu;wall=clock_s(CLOCK_MONOTONIC)-wall;uint64_t peak;
#ifdef __linux__
 peak=(uint64_t)status_kb("VmHWM:")*1024;
#else
 struct rusage ru;getrusage(RUSAGE_SELF,&ru);peak=ru.ru_maxrss;
#endif
 long rss=status_kb("VmRSS:"),vm=status_kb("VmSize:");f=fopen(argv[4],"wb");if(!f)return 3;wr(f,l,8,n*112);wr(f,c,8,n*112);wr(f,rows,1,n*14);wr(f,flips,1,n*2);wr(f,valid,1,n);wr(f,freq,8,n);fclose(f);int count=0,noise=0;for(uint64_t k=0;k<n;k++){count+=valid[k]!=0;if(k>=n-32)noise+=valid[k]!=0;}
 printf("{\"windows\":%llu,\"loops\":%d,\"iterations\":%d,\"cpu_seconds\":%.9f,\"wall_seconds\":%.9f,\"init_cpu_s\":%.9f,\"peak_rss_bytes\":%llu,\"resident_bytes\":%ld,\"virtual_bytes\":%ld,\"valid\":%d,\"noise_valid\":%d}\n",(unsigned long long)n,loops,iterations,cpu,wall,init,(unsigned long long)peak,rss*1024,vm*1024,count,noise);
}

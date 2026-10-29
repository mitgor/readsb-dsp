/* Common dlopen driver: identical input/output and timed boundary for C/Rust. */
#define _POSIX_C_SOURCE 200809L
#include <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/resource.h>
#ifdef __APPLE__
#include <mach/mach.h>
#endif
static double clk(clockid_t w){struct timespec t;clock_gettime(w,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static long memory(const char*key){
#ifdef __linux__
 FILE*f=fopen("/proc/self/status","r");char s[256];long n=0;if(!f)return 0;while(fgets(s,sizeof(s),f))if(!strncmp(s,key,strlen(key))){sscanf(s+strlen(key),"%ld",&n);break;}fclose(f);return n;
#else
 mach_task_basic_info_data_t i;mach_msg_type_number_t c=MACH_TASK_BASIC_INFO_COUNT;if(task_info(mach_task_self(),MACH_TASK_BASIC_INFO,(task_info_t)&i,&c)!=KERN_SUCCESS)return 0;return !strcmp(key,"VmSize:")?i.virtual_size/1024:i.resident_size/1024;
#endif
}
static void wr(FILE*f,const void*p,size_t size,size_t n){if(fwrite(p,size,n,f)!=n)exit(3);}
int main(int argc,char**argv){
 if(argc!=7)return 2;int loops=atoi(argv[3]),budget=atoi(argv[4]),mode=atoi(argv[5]);if(loops<1||loops>100000||budget<1||budget>256||mode<0||mode>1)return 2;
 void*h=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!h){fprintf(stderr,"%s\n",dlerror());return 3;}
 int(*scorefn)(const float*,int64_t,double,double,double,double*);int64_t(*selfn)(const float*,int64_t,int64_t,double,double,double,int,int64_t*,double*);
 void*s=dlsym(h,"rescue_extended_scores_neon");memcpy(&scorefn,&s,sizeof(s));s=dlsym(h,"rescue_extended_select_neon");memcpy(&selfn,&s,sizeof(s));if(!scorefn||!selfn)return 3;
 FILE*f=fopen(argv[2],"rb");uint64_t blocks=0;double weights[3];if(!f||fread(&blocks,8,1,f)!=1||blocks<1||blocks>1024||fread(weights,8,3,f)!=3)return 2;
 int64_t*n=calloc(blocks,8),*core=calloc(blocks,8),*counts=calloc(blocks,8);float**power=calloc(blocks,sizeof(float*));double**values=calloc(blocks,sizeof(double*));int64_t**ids=calloc(blocks,sizeof(int64_t*));uint64_t samples=0;
 for(uint64_t b=0;b<blocks;b++){
  if(fread(n+b,8,1,f)!=1||fread(core+b,8,1,f)!=1||n[b]<52||n[b]>10000051)return 2;power[b]=malloc(n[b]*4);if(!power[b]||fread(power[b],4,n[b],f)!=(size_t)n[b])return 2;
  int64_t size=mode?budget:n[b]-51;values[b]=malloc(size*8);ids[b]=malloc(budget*8);if(!values[b]||!ids[b])return 2;
  for(int64_t i=0;i<size;i++)values[b][i]=NAN;for(int i=0;i<budget;i++)ids[b][i]=-777;samples+=n[b];
 }fclose(f);
 double cpu=0,wall=0;for(int r=-2;r<loops;r++){
  if(r==0){cpu=clk(CLOCK_PROCESS_CPUTIME_ID);wall=clk(CLOCK_MONOTONIC);}
  for(uint64_t b=0;b<blocks;b++)counts[b]=mode?selfn(power[b],n[b],core[b],weights[0],weights[1],weights[2],budget,ids[b],values[b]):scorefn(power[b],n[b],weights[0],weights[1],weights[2],values[b]);
 }
 cpu=clk(CLOCK_PROCESS_CPUTIME_ID)-cpu;wall=clk(CLOCK_MONOTONIC)-wall;long rss=memory("VmRSS:"),vm=memory("VmSize:");f=fopen(argv[6],"wb");if(!f)return 3;wr(f,counts,8,blocks);int64_t selected=0,fallback=0;
 for(uint64_t b=0;b<blocks;b++){
  if(mode){wr(f,ids[b],8,budget);wr(f,values[b],8,budget);if(counts[b]>0)selected+=counts[b];if(counts[b]==-2)fallback++;}
  else wr(f,values[b],8,n[b]-51);
 }fclose(f);
 printf("{\"blocks\":%llu,\"samples\":%llu,\"loops\":%d,\"budget\":%d,\"mode\":%d,\"cpu_s\":%.9f,\"wall_s\":%.9f,\"resident_bytes\":%ld,\"virtual_bytes\":%ld,\"selected\":%lld,\"fallback_blocks\":%lld}\n",(unsigned long long)blocks,(unsigned long long)samples,loops,budget,mode,cpu,wall,rss*1024,vm*1024,(long long)selected,(long long)fallback);
}

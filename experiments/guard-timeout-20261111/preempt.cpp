#include <dlfcn.h>
#include <time.h>
#include <signal.h>
#include <unistd.h>
#include <vector>
#include <fstream>
#include <iostream>
#include <cstdint>
#include "incremental.h"
static bool armed=false;static int calls=0;
extern "C" int clock_gettime(clockid_t id,timespec *t) noexcept {
 using F=int(*)(clockid_t,timespec*);static F real=(F)dlsym(RTLD_NEXT,"clock_gettime");int rc=real(id,t);
 if(armed && id==CLOCK_MONOTONIC && ++calls==2)raise(SIGSTOP);
 return rc;
}
int main(int argc,char**argv){
 void *lib=dlopen(argv[1],RTLD_NOW);if(!lib)return 2;
 auto create=(void*(*)(int64_t,uint32_t))dlsym(lib,"stream1090_incremental_create");
 auto feed=(int(*)(void*,const uint8_t*,uint32_t,int64_t,stream1090_native_event*,uint32_t,uint32_t*,uint32_t))dlsym(lib,"stream1090_incremental_feed");
 auto destroy=(void(*)(void*))dlsym(lib,"stream1090_incremental_destroy");
 std::ifstream f(argv[2],std::ios::binary);std::vector<uint8_t> raw(96000);f.read((char*)raw.data(),raw.size());if(f.gcount()!=96000)return 3;
 auto ctx=create(0,48000);std::vector<stream1090_native_event> events(16384);uint32_t n=0;
 armed=true;int rc=feed(ctx,raw.data(),48000,0,events.data(),events.size(),&n,100000);armed=false;destroy(ctx);
 std::cout<<"{\"rc\":"<<rc<<",\"events\":"<<n<<",\"clock_calls\":"<<calls<<"}"<<std::endl;
}

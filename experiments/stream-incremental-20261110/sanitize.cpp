/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "incremental.h"
#include <cassert>
#include <cfenv>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <iterator>
#include <vector>
int main(int argc,char**argv){
 assert(argc==3);std::fenv_t before{},after{};std::fegetenv(&before);void*lib=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);assert(lib);std::fegetenv(&after);assert(std::memcmp(&before,&after,sizeof(before))==0);dlclose(lib);
 std::ifstream f(argv[2],std::ios::binary);std::vector<uint8_t> raw((std::istreambuf_iterator<char>(f)),{});assert(raw.size()==4802400);
 std::vector<stream1090_native_event> out(16384);void*c=stream1090_incremental_create(0,raw.size()/2);assert(c);uint32_t n=0,total=0;
 for(size_t at=0;at<raw.size()/2;){uint32_t size=std::min<size_t>(48000,raw.size()/2-at);assert(stream1090_incremental_feed(c,raw.data()+2*at,size,at,out.data(),out.size(),&n,0)==0);total+=n;at+=size;}
 assert(stream1090_incremental_finish(c,out.data(),out.size(),&n,0)==0);assert(total+n>=3);
 assert(stream1090_incremental_finish(c,out.data(),out.size(),&n,0)==-5 && n==0);stream1090_incremental_destroy(c);stream1090_incremental_destroy(nullptr);
}

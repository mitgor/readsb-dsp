/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "native.h"
#include <cassert>
#include <fstream>
#include <vector>
#include <iterator>
int main(int argc,char **argv) {
 assert(argc==2); std::ifstream in(argv[1],std::ios::binary);
 std::vector<uint8_t> iq((std::istreambuf_iterator<char>(in)),{});
 assert(!iq.empty());std::vector<stream1090_native_event> out(16384);uint32_t count=9;
 assert(stream1090_native_decode(iq.data(),iq.size()/2,0,out.data(),out.size(),&count)==0 && count>=3);
 assert(stream1090_native_decode(iq.data(),iq.size()/2,0,out.data(),1,&count)==-2 && count==0);
 assert(stream1090_native_decode(nullptr,0,0,nullptr,0,&count)==-1 && count==0);
 assert(stream1090_native_decode(iq.data(),iq.size()/2,-1,out.data(),out.size(),&count)==-1 && count==0);
}

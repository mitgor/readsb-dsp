/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <cfenv>
#include <cstring>
#include <cassert>
#include <dlfcn.h>
int main(int argc,char **argv) {
 assert(argc==2);std::fenv_t before{},after{};
 assert(std::fegetenv(&before)==0);
 void *lib=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);assert(lib);
 assert(std::fegetenv(&after)==0);
 assert(std::memcmp(&before,&after,sizeof(before))==0);
 assert(dlsym(lib,"stream1090_native_decode"));dlclose(lib);
}

// SPDX-License-Identifier: GPL-3.0-or-later
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <string>
#include "ShiftRegisters.hpp"
extern "C" uint64_t stream_shift8(uint64_t*,uint64_t*,uint32_t*,uint32_t*,const uint32_t*);
extern "C" uint64_t stream_shift8_c(uint64_t*,uint64_t*,uint32_t*,uint32_t*,const uint32_t*);
struct State:ShiftRegisters<8>{
 uint64_t c(const uint32_t* b){return stream_shift8_c(m_low,m_high,m_crc_56,m_crc_112,b);}
 uint64_t digest(){uint64_t x=0;for(int i=0;i<8;i++)x^=m_low[i]^m_high[i]^m_crc_56[i]^m_crc_112[i];return x;}
 uint64_t rust(const uint32_t* b){return stream_shift8(m_low,m_high,m_crc_56,m_crc_112,b);}
 bool same(const State& b){return memcmp(m_low,b.m_low,sizeof(m_low))==0&&memcmp(m_high,b.m_high,sizeof(m_high))==0&&memcmp(m_crc_56,b.m_crc_56,sizeof(m_crc_56))==0&&memcmp(m_crc_112,b.m_crc_112,sizeof(m_crc_112))==0;}
 void seed(uint64_t x){for(int i=0;i<8;i++){m_high[i]=x*(i+1);m_low[i]=~x*(i+1);m_crc_56[i]=(x+i)&0xffffff;m_crc_112[i]=(~x+i)&0xffffff;}}
};
int main(int argc,char**argv){
 uint64_t rng=0x8fa2197;auto next=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};uint32_t b[8];
 if(argc==1){
  for(int mode=0;mode<6;mode++){State c,r,abi;if(mode>=4){c.seed(mode==4?0:~uint64_t(0));r=c;abi=c;}
   for(int k=0;k<200000;k++){for(int j=0;j<8;j++)b[j]=mode==0?0:mode==1?1:mode==2?((k+j)&1):(next()&1);auto x=c.shiftInNewBits(b),y=r.rust(b);if(x!=y||!c.same(r)||abi.c(b)!=x||!c.same(abi)){fprintf(stderr,"mismatch %d %d\n",mode,k);return 2;}}
  }
  puts("{\"state_updates\":1200000,\"all_registers_crc_df_masks_exact\":true}");return 0;
 }
 // Identical offline workload. Initialization excluded; digest preserves outputs.
 State s;uint64_t digest=0;auto begin=std::chrono::steady_clock::now();bool rust=std::string(argv[1])=="rust";
 for(int k=0;k<4000000;k++){for(int j=0;j<8;j++)b[j]=next()&1;digest^=rust?s.rust(b):s.c(b);}
 printf("%llu\n",(unsigned long long)(digest^s.digest()));
}

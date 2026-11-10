/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <cstdint>
#include <cassert>
#include <memory>
#include "upstream/CRCErrorTable.hpp"
#include "upstream/ErasureRepair.hpp"
#include "upstream/ICAOCache.hpp"
int main() {
 // A non-table three-bit syndrome must be recovered by the bounded solver.
 uint8_t bits[]={11,37,63};uint32_t syndrome=0;
 for(auto b:bits)syndrome^=ErasureRepair::deltaTable()[b];
 assert(!CRC::df17ErrorTable.lookup(syndrome).valid());
 auto r=ErasureRepair::solve(syndrome,bits,3);assert(r.solved && r.mask==7);
 assert(!ErasureRepair::solve(syndrome,bits,0).solved);
 auto c=std::make_unique<ICAOTable>();constexpr uint32_t address=0x540621d;
 assert(!c->confirmTrustCandidate(address));
 for(int i=0;i<99;++i)c->tick();
 assert(!c->confirmTrustCandidate(address)); // same RF transmission cannot promote
 c->tick();assert(c->confirmTrustCandidate(address));
 auto it=c->insertWithCA(address);c->markAsSeen(it);assert(!c->isTrusted(it));
 c->markAsTrustedSeen(it);assert(c->isTrusted(it) && c->maybeTrusted(address));
 for(int i=0;i<31000000;++i)c->tick();assert(!c->isTrusted(it));
}

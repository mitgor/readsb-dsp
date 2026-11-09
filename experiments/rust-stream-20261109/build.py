"""Build isolated unchanged C++ control and single-kernel Rust substitution."""
from pathlib import Path
import argparse,subprocess,json,shutil,hashlib,platform
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--rustc',default='rustc');p.add_argument('--modes',nargs='*');p.add_argument('--selected-preset',action='store_true');a=p.parse_args();a.out=a.out.resolve();a.source=a.source.resolve();a.out.mkdir(parents=True,exist_ok=True);H=Path(__file__).parent.resolve();commands=[]
def run(cmd):
 commands.append([str(x) for x in cmd]);subprocess.run(cmd,check=True)
arch=['-mcpu=cortex-a76'] if platform.system()=='Linux' else []
flags=['-std=c++20','-O3','-DNDEBUG','-ffast-math',*arch,'-DSTATS_ENABLED=0','-DSTATS_END_ONLY=0','-DSTREAM1090_RSSI=1','-DSTREAM1090_PREAMBLE_GATE=1','-DSTREAM1090_PREAMBLE_THRESHOLD=1.2','-DSTREAM1090_MIN_SNR=2.5','-DSTREAM1090_PRESETS_FILE="DefaultPresets.hpp"']
run([a.rustc,'--edition=2021','--crate-type=staticlib','-C','opt-level=3','-C','panic=abort',*(['-C','target-cpu=cortex-a76'] if arch else []),H/'shift.rs','-o',a.out/'libshift.a'])
for mode in (a.modes if a.modes is not None else ['c','rust',*(['profile'] if arch else [])]):
 s=a.out/mode;shutil.copytree(a.source,s,dirs_exist_ok=True)
 if a.selected_preset:(s/'presets/DefaultPresets.hpp').write_text('ADD_PRESET(RtlSdr, 2.4, 8)\n')
 h=s/'include/ShiftRegisters.hpp';text=h.read_text()
 if mode=='rust':
  text=text.replace('#include "CRC.hpp"','#include "CRC.hpp"\nextern "C" uint64_t stream_shift8(uint64_t*,uint64_t*,uint32_t*,uint32_t*,const uint32_t*);')
  text=text.replace('uint64_t handledMask = 0;','if constexpr(NumStreams == 8) { return stream_shift8(this->m_low,this->m_high,this->m_crc_56,this->m_crc_112,cmp); }\n            uint64_t handledMask = 0;');h.write_text(text)
 if mode=='profile':
  text=text.replace('uint64_t shiftInNewBits(', '__attribute__((noinline)) uint64_t shiftInNewBits(');h.write_text(text)
 extra=['-pg','-g'] if mode=='profile' else []
 run(['c++',*flags,*extra,'-I'+str(s/'include'),'-I'+str(s/'presets'),s/'main.cpp',*([a.out/'libshift.a','-lpthread',*(['-ldl'] if arch else []),'-lm'] if mode=='rust' else []),'-o',a.out/('stream-'+mode)])
# ABI-matched standalone C++ kernel; separate translation unit prevents dead CRC elimination.
h=(a.source/'include/ShiftRegisters.hpp').read_text();body=h.split('uint64_t handledMask = 0;',1)[1].split('return handledMask;',1)[0]
for old,new in [('this->m_low','lows'),('this->m_high','highs'),('this->m_crc_56','c56'),('this->m_crc_112','c112')]:body=body.replace(old,new)
body=body.replace('NumStreams','8')
(a.out/'kernel_c.cpp').write_text('#include <cstdint>\nextern "C" uint64_t stream_shift8_c(uint64_t* lows,uint64_t* highs,uint32_t* c56,uint32_t* c112,const uint32_t* cmp) { constexpr uint32_t Delta55=0x18567, Delta111=0x3935ea, Polynomial=0x1fff409,handledDownlinkFormats=0x3f0831;uint64_t handledMask=0;'+body+'return handledMask;}')
run(['c++',*flags,'-I'+str(a.source/'include'),'-I'+str(a.source/'presets'),H/'state_test.cpp',a.out/'kernel_c.cpp',a.out/'libshift.a','-lpthread',*(['-ldl'] if arch else []),'-lm','-o',a.out/'state-test'])
(a.out/'build.json').write_text(json.dumps(dict(commands=commands,rustc=subprocess.check_output([a.rustc,'--version','--verbose'],text=True),cxx=subprocess.check_output(['c++','--version'],text=True),source_sha256={str(x.relative_to(a.source)):hashlib.sha256(x.read_bytes()).hexdigest() for x in a.source.rglob('*') if x.is_file()}),indent=2)+'\n')

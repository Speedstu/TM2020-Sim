// Ephemeral discovery in a private Unicorn engine. This is deliberately a
// different DLL/API from the offline coverage guard: discovery never weakens
// the guard or authorizes an uncaptured byte during offline replay.
#include <unicorn/unicorn.h>
#include <unicorn/x86.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <map>
#include <new>
#include <set>
#include <vector>
#define EXPORT extern "C" __declspec(dllexport)
struct Api {
  decltype(&uc_hook_add) hook_add; decltype(&uc_hook_del) hook_del;
  decltype(&uc_mem_read) mem_read; decltype(&uc_reg_read) reg_read;
  decltype(&uc_emu_stop) emu_stop;
};
struct Fault {std::uint64_t kind{},address{},start{},size{},pc{};};
struct Coverage {std::array<unsigned char,4096> data{},executed{},written{};};
struct Capture {
  uc_engine* uc; Api api; uc_hook code_hook{},memory_hook{};
  std::map<std::uint64_t,std::array<unsigned char,4096>> code;
  std::map<std::uint64_t,Coverage> coverage;
  std::vector<std::pair<std::uint64_t,std::uint64_t>> excluded;
  std::set<std::uint64_t> platform;
  Fault fault; std::uint64_t instructions{},accesses{};
  bool ignored(std::uint64_t at) const {
    return std::any_of(excluded.begin(),excluded.end(),[at](const auto& r){return at>=r.first&&at-r.first<r.second;});
  }
  void fail(std::uint64_t kind,std::uint64_t at,std::uint64_t start,std::uint64_t size) noexcept {
    if(!fault.kind){std::uint64_t pc{};api.reg_read(uc,UC_X86_REG_RIP,&pc);fault={kind,at,start,size,pc};}
    api.emu_stop(uc);
  }
  Coverage& page(std::uint64_t at) {
    if(!coverage.contains(at)&&coverage.size()>=16384)throw std::bad_alloc();
    return coverage[at];
  }
  static void memory(uc_engine*,uc_mem_type access,std::uint64_t address,int size,std::int64_t,void* user) noexcept {
    auto& g=*static_cast<Capture*>(user);
    try {
      ++g.accesses;if(g.fault.kind){g.api.emu_stop(g.uc);return;}
      if(size<=0||address>UINT64_MAX-std::uint64_t(size)){g.fail(3,address,address,size);return;}
      for(auto at=address;at<address+size;) {
        const auto n=std::min<std::uint64_t>(address+size-at,4096-(at&4095));
        if(!g.ignored(at)) {
          auto& p=g.page(at&~4095ull);
          std::fill_n(p.data.begin()+(at&4095),n,1);
          if(access==UC_MEM_WRITE)std::fill_n(p.written.begin()+(at&4095),n,1);
        }
        at+=n;
      }
    }catch(...){g.fail(3,address,address,size);}
  }
  static void instruction(uc_engine*,std::uint64_t address,std::uint32_t size,void* user) noexcept {
    auto& g=*static_cast<Capture*>(user);
    try {
      ++g.instructions;if(g.fault.kind){g.api.emu_stop(g.uc);return;}
      if(g.platform.contains(address))return;
      if(size<1||size>15||address>UINT64_MAX-size){g.fail(2,address,address,size);return;}
      unsigned char raw[15];
      if(g.api.mem_read(g.uc,address,raw,size)!=UC_ERR_OK){g.fail(2,address,address,size);return;}
      for(unsigned i=0;i<size;++i) {
        auto expected=g.code.find((address+i)&~4095ull);
        if(expected==g.code.end()||raw[i]!=expected->second[(address+i)&4095]){g.fail(2,address+i,address,size);return;}
        g.page((address+i)&~4095ull).executed[(address+i)&4095]=1;
      }
    }catch(...){g.fail(3,address,address,size);}
  }
};
EXPORT Capture* tmcapture_create(uc_engine* uc,const Api* api) noexcept {
  if(!uc||!api||!api->hook_add||!api->hook_del||!api->mem_read||!api->reg_read||!api->emu_stop)return nullptr;
  return new(std::nothrow) Capture{uc,*api};
}
EXPORT int tmcapture_code(Capture* g,std::uint64_t page,const unsigned char* bytes) noexcept {
  if(!g||!bytes||page%4096)return 0;
  try {if(g->code.size()>=16384&&!g->code.contains(page))return 0;
    std::memcpy(g->code[page].data(),bytes,4096);return 1;}catch(...){return 0;}
}
EXPORT int tmcapture_exclude(Capture* g,std::uint64_t at,std::uint64_t size) noexcept {
  if(!g||at%4096||!size||size%4096||at>UINT64_MAX-size)return 0;
  try {g->excluded.emplace_back(at,size);return 1;}catch(...){return 0;}
}
EXPORT int tmcapture_platform(Capture* g,std::uint64_t address) noexcept {
  try {if(!g)return 0;g->platform.insert(address);return 1;}catch(...){return 0;}
}
EXPORT int tmcapture_start(Capture* g) noexcept {
  if(!g||g->code_hook||g->memory_hook)return 0;
  if(g->api.hook_add(g->uc,&g->code_hook,UC_HOOK_CODE,reinterpret_cast<void*>(&Capture::instruction),g,1,0)!=UC_ERR_OK)return 0;
  if(g->api.hook_add(g->uc,&g->memory_hook,UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,reinterpret_cast<void*>(&Capture::memory),g,1,0)!=UC_ERR_OK){
    g->api.hook_del(g->uc,g->code_hook);g->code_hook=0;return 0;}
  return 1;
}
EXPORT std::uint64_t tmcapture_pages(Capture* g,std::uint64_t* out,std::uint64_t capacity) noexcept {
  if(!g)return 0;
  if(out&&capacity>=g->coverage.size()){std::size_t i=0;for(const auto& p:g->coverage)out[i++]=p.first;}
  return g->coverage.size();
}
EXPORT int tmcapture_mask(Capture* g,std::uint64_t page,unsigned char* out,int plane) noexcept {
  if(!g||!out||plane<0||plane>2)return 0;
  auto it=g->coverage.find(page);if(it==g->coverage.end())return 0;
  std::memcpy(out,plane==0?it->second.data.data():plane==1?it->second.executed.data():it->second.written.data(),4096);return 1;
}
EXPORT int tmcapture_fault(Capture* g,Fault* out) noexcept {if(!g||!out)return -1;*out=g->fault;return g->fault.kind!=0;}
EXPORT void tmcapture_counts(Capture* g,std::uint64_t* out) noexcept {if(g&&out){out[0]=g->instructions;out[1]=g->accesses;}}
EXPORT void tmcapture_destroy(Capture* g) noexcept {
  if(!g)return;
  if(g->code_hook)g->api.hook_del(g->uc,g->code_hook);
  if(g->memory_hook)g->api.hook_del(g->uc,g->memory_hook);
  delete g;
}
EXPORT void tmcapture_abandon(Capture* g) noexcept {delete g;}

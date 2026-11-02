// Guards our private Unicorn instance only. No game handles or instruction patches.
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
  decltype(&uc_hook_add) hook_add;
  decltype(&uc_hook_del) hook_del;
  decltype(&uc_mem_read) mem_read;
  decltype(&uc_reg_read) reg_read;
  decltype(&uc_emu_stop) emu_stop;
};
struct Fault {
  std::uint64_t kind{}, address{}, start{}, size{}, pc{};
};
struct Guard {
  uc_engine* uc;
  Api api;
  uc_hook code_hook{}, memory_hook{};
  std::map<std::uint64_t, std::array<unsigned char,4096>> masks, code, initialized;
  std::vector<std::pair<std::uint64_t,std::uint64_t>> synthetic, excluded;
  std::set<std::uint64_t> platform, touched;
  Fault fault;
  std::uint64_t instruction_count{}, access_count{};
  bool initialize_writes{};
  bool inside(std::uint64_t at, const auto& ranges) const {
    return std::any_of(ranges.begin(),ranges.end(),[at](const auto& r) {
      return at >= r.first && at-r.first < r.second;
    });
  }
  void fail(std::uint64_t kind, std::uint64_t at,
            std::uint64_t start, std::uint64_t size, std::uint64_t pc=0) noexcept {
    if (!fault.kind) {
      if (!pc) api.reg_read(uc, UC_X86_REG_RIP, &pc);
      fault={kind,at,start,size,pc};
    }
    api.emu_stop(uc);
  }
  static void on_memory(uc_engine*, uc_mem_type access, std::uint64_t address,
                        int size, std::int64_t, void* user) noexcept {
    auto& g=*static_cast<Guard*>(user);
    try {
      ++g.access_count;
      if(g.fault.kind) {g.api.emu_stop(g.uc);return;}
      if(size<=0 || address>UINT64_MAX-std::uint64_t(size)) {
        g.fail(3,address,address,size);return;
      }
      const auto end=address+size;
      // Preserve the Python guard's dirty-page accounting, including failed reads.
      for(auto page=address&~4095ull;page<end;page+=4096)
        if(g.inside(page,g.synthetic)) g.touched.insert(page);
      for(auto at=address;at<end;) {
        const auto page=at&~4095ull;
        auto count=std::min<std::uint64_t>(end-at,4096-(at&4095));
        // Excluded arenas are page aligned and verified when registered.
        if(!g.inside(at,g.excluded) && !g.code.contains(page)) {
          const auto it=g.masks.find(page);
          const bool may_write=g.initialize_writes && access==UC_MEM_WRITE &&
                               (it!=g.masks.end() || g.inside(page,g.synthetic));
          if(may_write) {
            auto& generated=g.initialized[page];
            for(std::uint64_t i=0;i<count;++i)generated[(at&4095)+i]=1;
          } else {
            auto generated=g.initialized.find(page);
            for(std::uint64_t i=0;i<count;++i) {
              const auto offset=(at&4095)+i;
              if((it==g.masks.end() || it->second[offset]!=1) &&
                 (generated==g.initialized.end() || generated->second[offset]!=1)) {
                g.fail(1,at+i,address,size);return;
              }
            }
          }
        }
        at+=count;
      }
    } catch(...) {g.fail(3,address,address,size);}
  }
  static void on_code(uc_engine*, std::uint64_t address,
                      std::uint32_t size, void* user) noexcept {
    auto& g=*static_cast<Guard*>(user);
    ++g.instruction_count;
    if(g.fault.kind) {g.api.emu_stop(g.uc);return;}
    if(g.platform.contains(address)) return;
    if(!size || size>15 || address>UINT64_MAX-size) {
      g.fail(2,address,address,size,address);return;
    }
    unsigned char raw[15];
    if(g.api.mem_read(g.uc,address,raw,size)!=UC_ERR_OK) {
      g.fail(2,address,address,size,address);return;
    }
    for(std::uint32_t i=0;i<size;++i) {
      auto it=g.code.find((address+i)&~4095ull);
      if(it==g.code.end() || raw[i]!=it->second[(address+i)&4095]) {
        g.fail(2,address+i,address,size,address);return;
      }
    }
  }
};
EXPORT Guard* tmguard_create(uc_engine* uc, const Api* api) noexcept {
  if(!uc || !api || !api->hook_add || !api->hook_del || !api->mem_read ||
     !api->reg_read || !api->emu_stop) return nullptr;
  auto* g=new(std::nothrow) Guard{uc,*api};
  return g;
}
EXPORT int tmguard_page(Guard* g, std::uint64_t page,
                        const unsigned char* bytes, int code) noexcept {
  if(!g || !bytes || page%4096) return 0;
  try {
    auto& out=code?g->code[page]:g->masks[page];
    std::memcpy(out.data(),bytes,4096);return 1;
  } catch(...) {return 0;}
}
EXPORT int tmguard_range(Guard* g, std::uint64_t at,
                         std::uint64_t size, int excluded) noexcept {
  if(!g || at%4096 || !size || size%4096 || at>UINT64_MAX-size) return 0;
  try {(excluded?g->excluded:g->synthetic).emplace_back(at,size);return 1;}
  catch(...) {return 0;}
}
EXPORT int tmguard_platform(Guard* g, std::uint64_t at) noexcept {
  try {if(!g)return 0;g->platform.insert(at);return 1;}catch(...) {return 0;}
}
EXPORT int tmguard_start(Guard* g) noexcept {
  if(!g || g->code_hook || g->memory_hook) return 0;
  if(g->api.hook_add(g->uc,&g->code_hook,UC_HOOK_CODE,
         reinterpret_cast<void*>(&Guard::on_code),g,1,0)!=UC_ERR_OK) return 0;
  if(g->api.hook_add(g->uc,&g->memory_hook,UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,
         reinterpret_cast<void*>(&Guard::on_memory),g,1,0)!=UC_ERR_OK) {
    g->api.hook_del(g->uc,g->code_hook);g->code_hook=0;return 0;
  }
  return 1;
}
EXPORT int tmguard_fault(Guard* g, Fault* out) noexcept {
  if(!g || !out)return -1;*out=g->fault;return g->fault.kind!=0;
}
EXPORT std::uint64_t tmguard_touched(Guard* g, std::uint64_t* out,
                                   std::uint64_t capacity) noexcept {
  if(!g) return 0;
  if(out && capacity>=g->touched.size()) std::copy(g->touched.begin(),g->touched.end(),out);
  return g->touched.size();
}
EXPORT void tmguard_clear(Guard* g) noexcept {
  if(g) {g->fault={};g->touched.clear();g->initialized.clear();}
}
EXPORT void tmguard_write_initialization(Guard* g,int enabled) noexcept {
  if(g)g->initialize_writes=enabled!=0;
}
EXPORT void tmguard_access(Guard* g,std::uint64_t address,int size,int write) noexcept {
  if(g)Guard::on_memory(g->uc,write?UC_MEM_WRITE:UC_MEM_READ,address,size,0,g);
}
EXPORT std::uint64_t tmguard_initialized_pages(Guard* g,std::uint64_t* pages,
                                             std::uint64_t capacity) noexcept {
  if(!g)return 0;
  if(pages && capacity>=g->initialized.size()) {
    std::size_t i=0;for(const auto& [page,mask]:g->initialized)pages[i++]=page;
  }
  return g->initialized.size();
}
EXPORT int tmguard_initialized_mask(Guard* g,std::uint64_t page,
                                    unsigned char* bytes,int restore) noexcept {
  if(!g||!bytes||page%4096)return 0;
  try {
    if(restore) {
      if(!g->initialize_writes || (!g->masks.contains(page)&&!g->inside(page,g->synthetic)))return 0;
      if(std::any_of(bytes,bytes+4096,[](auto b){return b>1;}))return 0;
      std::memcpy(g->initialized[page].data(),bytes,4096);
    } else {
      auto it=g->initialized.find(page);if(it==g->initialized.end())return 0;
      std::memcpy(bytes,it->second.data(),4096);
    }
    return 1;
  }catch(...) {return 0;}
}
EXPORT void tmguard_counts(Guard* g, std::uint64_t* out) noexcept {
  if(g && out) {out[0]=g->instruction_count;out[1]=g->access_count;}
}
EXPORT void tmguard_destroy(Guard* g) noexcept {
  if(!g)return;
  if(g->code_hook)g->api.hook_del(g->uc,g->code_hook);
  if(g->memory_hook)g->api.hook_del(g->uc,g->memory_hook);
  delete g;
}
// When Python collects an unreachable engine/callback cycle, the engine's own
// finalizer owns uc_close and all hook deletion. Never touch that dead handle.
EXPORT void tmguard_abandon(Guard* g) noexcept {delete g;}

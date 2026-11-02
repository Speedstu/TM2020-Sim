#include "tm2020/read_only_live.hpp"
#include "tm2020/recovered_rigid.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <intrin.h>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <vector>
#if defined(_MSC_VER)
#pragma section(".tls$BBB", read, write)
__declspec(allocate(".tls$BBB")) unsigned char owned_step_tls[0x4000]{};
#else
__attribute__((section(".tls$BBB"),
               used)) unsigned char owned_step_tls[0x4000]{};
#endif
void check(bool ok, const char *why) {
  if (!ok)
    throw std::runtime_error(why);
}
struct Reader {
  std::ifstream f;
  explicit Reader(const char *p) : f(p, std::ios::binary) {
    check(bool(f), "Cannot read fixture");
  }
  void read(void *p, std::size_t n) {
    check(n <= 16 * 1024 * 1024, "Read bound");
    f.read(static_cast<char *>(p), std::streamsize(n));
    check(bool(f), "Truncated fixture");
  }
  template <class T> T get() {
    T v{};
    read(&v, sizeof(v));
    return v;
  }
};
struct Memory {
  std::vector<void *> owned;
  ~Memory() {
    for (auto p : owned)
      VirtualFree(p, 0, MEM_RELEASE);
  }
  void reserve(std::uint64_t at, std::size_t size) {
    auto p = VirtualAlloc(reinterpret_cast<void *>(at), size, MEM_RESERVE,
                          PAGE_NOACCESS);
    check(p == reinterpret_cast<void *>(at), "Owned address range unavailable");
    owned.push_back(p);
  }
  void commit(std::uint64_t at, std::size_t size = 4096) {
    check(VirtualAlloc(reinterpret_cast<void *>(at), size, MEM_COMMIT,
                       PAGE_READWRITE) == reinterpret_cast<void *>(at),
          "Cannot commit owned memory");
  }
};
using Page = std::array<unsigned char, 4096>;
struct Data {
  std::uint64_t address;
  Page initial;
};
struct Output {
  std::uint64_t address;
  std::vector<unsigned char> mask, expected;
};

std::string hex(const std::array<unsigned char, 32> &b) {
  std::string s;
  for (auto c : b) {
    s += "0123456789abcdef"[c >> 4];
    s += "0123456789abcdef"[c & 15];
  }
  return s;
}

struct Allocation {
  std::uint64_t pointer{}, size{};
};
static std::array<Allocation, 16384> allocations{};
static unsigned allocation_count{};
static std::uint64_t cursor = 0x800000000ull;
static std::array<std::uint64_t, 4> api{};
static DWORD simulation_thread{};
static volatile bool in_original = false;
[[noreturn]] void bridge_error(const char *what, std::uint64_t value = 0) {
  char buffer[256]{};
  in_original = false;
  const auto n = std::snprintf(buffer, sizeof(buffer),
                               "OWNED_PLATFORM_BRIDGE_ERROR %s value=0x%llx\n",
                               what, static_cast<unsigned long long>(value));
  DWORD written{};
  WriteFile(GetStdHandle(STD_ERROR_HANDLE), buffer, DWORD(n), &written,
            nullptr);
  in_original = false;
  ExitProcess(24);
}
Allocation *lookup(std::uint64_t pointer) {
  for (unsigned i = 0; i < allocation_count; ++i)
    if (allocations[i].pointer == pointer)
      return &allocations[i];
  return nullptr;
}
std::uint64_t allocate(std::uint64_t count) {
  const auto at = (cursor + 15) & ~std::uint64_t(15);
  if (count > 4 * 1024 * 1024 ||
      at + std::max<std::uint64_t>(1, count) > 0x804000000ull ||
      allocation_count >= allocations.size())
    bridge_error("allocation bound", count);
  cursor = at + std::max<std::uint64_t>(1, count);
  allocations[allocation_count++] = {at, count};
  return at;
}
LONG CALLBACK fault(EXCEPTION_POINTERS *p) {
  auto &c = *p->ContextRecord;
  if(!in_original && (p->ExceptionRecord->ExceptionCode==0x20474343u ||
                      p->ExceptionRecord->ExceptionCode==0xe06d7363u))
    return EXCEPTION_CONTINUE_SEARCH;
  if (p->ExceptionRecord->ExceptionCode == EXCEPTION_SINGLE_STEP &&
      GetCurrentThreadId() == simulation_thread) {
    unsigned which = 4;
    for (unsigned n = 0; n < api.size(); ++n)
      if (c.Rip == api[n])
        which = n;
    if (which < 4) {
      c.Dr6 = 0;
      if (!in_original) {
        c.EFlags |= 1u << 16;
        return EXCEPTION_CONTINUE_EXECUTION;
      }
      std::uint64_t result{};
      if (which == 0)
        result = allocate(c.R8);
      if (which == 1) {
        const auto pointer = c.R8, count = c.R9, flags = c.Rdx;
        auto *old = lookup(pointer);
        if (!old)
          bridge_error("unknown reallocation", pointer);
        if (count <= old->size) {
          old->size = count;
          result = pointer;
        } else if (flags & 0x10)
          result = 0;
        else {
          const auto old_size = old->size;
          result = allocate(count);
          std::memcpy(reinterpret_cast<void *>(result),
                      reinterpret_cast<const void *>(pointer),
                      std::size_t(std::min(count, old_size)));
          old->pointer = 0;
        }
      }
      if (which == 2) {
        if (c.R8) {
          auto *old = lookup(c.R8);
          if (!old)
            bridge_error("unknown free", c.R8);
          old->pointer = 0;
        }
        result = 1;
      }
      if (which == 3) {
        auto *old = lookup(c.R8);
        if (!old)
          bridge_error("unknown size query", c.R8);
        result = old->size;
      }
      c.Rax = result;
      c.Rip = *reinterpret_cast<const std::uint64_t *>(c.Rsp);
      c.Rsp += 8;
      return EXCEPTION_CONTINUE_EXECUTION;
    }
  }
  char buffer[256]{};
  const auto n = std::snprintf(
      buffer, sizeof(buffer),
      "OWNED_STEP_FAULT code=0x%lx rip=0x%llx arg0=0x%llx arg1=0x%llx\n",
      p->ExceptionRecord->ExceptionCode, static_cast<unsigned long long>(c.Rip),
      static_cast<unsigned long long>(
          p->ExceptionRecord->ExceptionInformation[0]),
      static_cast<unsigned long long>(
          p->ExceptionRecord->ExceptionInformation[1]));
  DWORD written{};
  WriteFile(GetStdHandle(STD_ERROR_HANDLE), buffer, DWORD(n), &written,
            nullptr);
  in_original = false;
  ExitProcess(23);
  return EXCEPTION_CONTINUE_SEARCH;
}
void initialize_owned_tls() {
  const auto *self =
      reinterpret_cast<const unsigned char *>(GetModuleHandleW(nullptr));
  const auto *sd = reinterpret_cast<const IMAGE_DOS_HEADER *>(self);
  const auto *sn =
      reinterpret_cast<const IMAGE_NT_HEADERS64 *>(self + sd->e_lfanew);
  auto dir = sn->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS];
  check(dir.VirtualAddress && dir.Size >= sizeof(IMAGE_TLS_DIRECTORY64),
        "Missing owned TLS");
  const auto *tls = reinterpret_cast<const IMAGE_TLS_DIRECTORY64 *>(
      self + dir.VirtualAddress);
  check(*reinterpret_cast<const DWORD *>(tls->AddressOfIndex) == 0 &&
            tls->EndAddressOfRawData - tls->StartAddressOfRawData >= 0x4000,
        "Wrong owned TLS template");
  const auto *table =
      reinterpret_cast<const std::uintptr_t *>(__readgsqword(0x58));
  check(table && table[0], "Missing TLS block");
  auto *block = reinterpret_cast<unsigned char *>(table[0]);
  const auto own_offset=reinterpret_cast<std::uintptr_t>(owned_step_tls)-tls->StartAddressOfRawData;
  check(own_offset<=0x148 && own_offset+sizeof(owned_step_tls)<=
        tls->EndAddressOfRawData-tls->StartAddressOfRawData,
        "Owned TLS storage does not cover the constructed context");
  std::memset(block+own_offset,0,sizeof(owned_step_tls));
  check(*reinterpret_cast<std::uintptr_t *>(block + 0x1b8) == 0,
        "Profiler null branch unavailable");
  static std::array<unsigned char, 0x400> thread_context{};
  thread_context.fill(0);
  const auto thread_pointer =
      reinterpret_cast<std::uintptr_t>(thread_context.data());
  std::memcpy(block + 0x148, &thread_pointer, 8);
  const std::array<std::uint64_t, 4> arena{0x600000000, 0x601000000,
                                           0x600000000, 0x601000000};
  std::memcpy(block + 0x160, arena.data(), 32);
  std::uint32_t diagnose{};
  std::memcpy(block + 0x180, &diagnose, 4);
}
struct SimulationJob {
  std::uint64_t base, manager, states;
  std::array<std::uint32_t, 3> timing;
  unsigned long ticks, referenceTicks;
  std::vector<Output> *outputs;
  std::uint64_t control_vehicle{};
  std::array<float, 4> controls{};
  bool hold_controls{};
  bool hold_action_axis{};
  std::vector<std::array<float, 3>> control_schedule;
  std::uint32_t steering_offset{0x1430};
  bool firstExact{};
  unsigned framesCompared{};
  double elapsedSeconds{};
  const std::vector<Data>* initial_pages{};
  std::uint64_t heap_binding{},heap_handle{};
  unsigned episodes{1},episodesCompared{};
  std::uint64_t totalFramesCompared{};
  unsigned pipelineVersion{};
  std::uint64_t collisionWorld{},registeredForceContext{};
};
DWORD WINAPI simulate(void *raw) try {
  auto &job = *static_cast<SimulationJob *>(raw);
  using Fn = void (*)(void *, const void *);
  auto step = reinterpret_cast<Fn>(job.base + 0x7bd0e0);
  const auto started = std::chrono::steady_clock::now();
  const auto initial_timing=job.timing;
  for(unsigned episode=0;episode<job.episodes;++episode){
  if(episode){
    // These arenas start zeroed in the emulator. Restoring sparse captured
    // pages alone leaves stale bytes in otherwise unobserved scratch pages.
    for(const auto [address,size]:std::array<std::pair<std::uint64_t,std::size_t>,3>{
          {{0x600000000ull,0x1000000},{0x700000000ull,0x4000000},
           {0x800000000ull,0x4000000}}}){
      check(VirtualFree(reinterpret_cast<void*>(address),size,MEM_DECOMMIT)!=0,
            "Cannot clear owned reset arena");
      check(VirtualAlloc(reinterpret_cast<void*>(address),size,MEM_COMMIT,PAGE_READWRITE)
              ==reinterpret_cast<void*>(address),"Cannot restore owned reset arena");
    }
    for(const auto& page:*job.initial_pages)
      std::memcpy(reinterpret_cast<void*>(page.address),page.initial.data(),4096);
    if(job.heap_binding)
      std::memcpy(reinterpret_cast<void*>(job.heap_binding),&job.heap_handle,8);
  }
  allocation_count=0;allocations.fill({});cursor=0x800000000ull;
  initialize_owned_tls();_mm_setcsr(0x1f80);
  job.timing=initial_timing;job.framesCompared=0;job.firstExact=false;
  for (unsigned long tick = 0; tick < job.ticks; ++tick) {
    if (tick)
      job.timing[0] += 10;
    if (!job.control_schedule.empty()) {
      const auto &controls = job.control_schedule.at(std::size_t(tick));
      auto *vehicle = reinterpret_cast<unsigned char *>(job.control_vehicle);
      std::memcpy(vehicle + 0x98, &controls[0], sizeof(float));
      std::memcpy(vehicle + 0x9c, &controls[1], sizeof(float));
      std::memcpy(vehicle + job.steering_offset, &controls[2], sizeof(float));
    } else if (job.hold_controls) {
      auto *vehicle = reinterpret_cast<unsigned char *>(job.control_vehicle);
      std::memcpy(vehicle + 0x98, &job.controls[0], sizeof(float));
      std::memcpy(vehicle + 0x9c, &job.controls[1], sizeof(float));
      std::memcpy(vehicle + job.steering_offset, &job.controls[2], sizeof(float));
    }
    if (job.hold_action_axis)
      std::memcpy(reinterpret_cast<void *>(job.control_vehicle + 0x1374),
                  &job.controls[3], sizeof(float));
    in_original = true;
    if(job.pipelineVersion==4){
      using Unary=void(*)(void*);
      for(const unsigned entry:{0x2a6360u,0x2a6960u})
        reinterpret_cast<Unary>(job.base+entry)(reinterpret_cast<void*>(job.collisionWorld));
    }
    if(job.pipelineVersion>=2)
      reinterpret_cast<Fn>(job.base+0x1501f00)(
          reinterpret_cast<void*>(job.registeredForceContext),job.timing.data());
    step(reinterpret_cast<void *>(job.manager), job.timing.data());
    if(job.pipelineVersion){
      using Unary=void(*)(void*);
      reinterpret_cast<Unary>(job.base+0x2a9b50)(reinterpret_cast<void*>(job.collisionWorld));
      reinterpret_cast<Unary>(job.base+0x7bfcb0)(reinterpret_cast<void*>(job.manager));
      reinterpret_cast<Fn>(job.base+0x7d2b90)(
          reinterpret_cast<void*>(job.registeredForceContext),job.timing.data());
      if(job.pipelineVersion>=2){
        using Post=void(*)(void*,void*,std::uint32_t,float);
        reinterpret_cast<Post>(job.base+0x1501f50)(reinterpret_cast<void*>(job.registeredForceContext),
            reinterpret_cast<void*>(job.manager),job.timing[0],std::bit_cast<float>(job.timing[2]));
        if(job.pipelineVersion>=3)
          reinterpret_cast<Unary>(job.base+0x7d2cf0)(reinterpret_cast<void*>(job.registeredForceContext));
      }
    }
    in_original = false;
    {
      unsigned differences{};
      for (const auto &o : *job.outputs) {
        const auto *actual = reinterpret_cast<const unsigned char *>(o.address);
        for (std::size_t i = 0; i < o.mask.size(); ++i)
          if (o.mask[i] &&
              actual[i] != o.expected[std::size_t(tick) * o.mask.size() + i]) {
            if (differences < 16)
              std::cerr
                  << "OUTPUT_DIFFERENCE frame=" << tick << " address=0x"
                  << std::hex << o.address + i << std::dec
                  << " native=" << unsigned(actual[i]) << " expected="
                  << unsigned(o.expected[std::size_t(tick) * o.mask.size() + i])
                  << '\n';
            ++differences;
          }
      }
      check(differences == 0, "Reference physics output differs");
      ++job.framesCompared;
      if (tick + 1 == job.referenceTicks) {
        job.firstExact = true;
        if(episode==0)std::cout << "PASS REFERENCE_SEQUENCE_BIT_EXACT every_frame=true "
                     "allocator_bridge_owned_thread=true"
                  << std::endl;
      }
    }
    if (episode==0 && tick % 10 == 0) {
      std::array<float, 3> position{}, velocity{};
      std::memcpy(position.data(),
                  reinterpret_cast<const void *>(job.states + 0x24), 12);
      std::memcpy(velocity.data(),
                  reinterpret_cast<const void *>(job.states + 0x40), 12);
      std::cout << "TICK " << tick + 1 << " pos=" << position[0] << ','
                << position[1] << ',' << position[2] << " vel=" << velocity[0]
                << ',' << velocity[1] << ',' << velocity[2] << std::endl;
    }
  }
  check(job.firstExact && job.framesCompared==job.referenceTicks,"Reset episode trace incomplete");
  ++job.episodesCompared;job.totalFramesCompared+=job.framesCompared;
  if(job.episodes>1 && (episode==0 || (episode+1)%1000==0 || episode+1==job.episodes))
    std::cout<<"RESET_EPISODE "<<episode+1<<" every_frame_bit_exact=true\n";
  }
  job.elapsedSeconds =
      std::chrono::duration<double>(std::chrono::steady_clock::now() - started)
          .count();
  return 0;
}catch(const std::exception& e){
  in_original=false;
  std::cerr<<"OWNED_SIMULATION_ERROR "<<e.what()<<'\n';return 1;
}
int main(int argc, char **argv) try {
  check(argc == 4 || argc==6, "Usage: tm2020_original_step_native original.exe "
                   "fixture.tmstepnative report.json [--episodes count]");
  unsigned episodes=1;
  if(argc==6){
    check(std::string(argv[4])=="--episodes","Unknown runtime option");
    const std::string value=argv[5];std::size_t consumed{};
    const auto parsed=std::stoull(value,&consumed);
    check(consumed==value.size() && parsed>=1 && parsed<=10000,"Reset episode count outside [1,10000]");
    episodes=static_cast<unsigned>(parsed);
  }
  Reader r(argv[2]);
  const auto magic = r.get<std::array<char, 8>>();
  const auto version = r.get<std::uint32_t>();
  check((magic == std::array<char, 8>{'T', 'M', 'S', 'T', 'N', 'V', '3', 0} && version == 3) ||
            (magic == std::array<char, 8>{'T', 'M', 'S', 'T', 'N', 'V', '4', 0} && version == 4) ||
            (magic == std::array<char, 8>{'T', 'M', 'S', 'T', 'N', 'V', '5', 0} && version == 5) ||
            (magic == std::array<char, 8>{'T', 'M', 'S', 'T', 'N', 'V', '6', 0} && version == 6) ||
            (magic == std::array<char, 8>{'T', 'M', 'S', 'T', 'N', 'V', '7', 0} && version == 7),
        "Unknown fixture format");
  const auto game_sha = hex(r.get<std::array<unsigned char, 32>>()),
             nt_sha = hex(r.get<std::array<unsigned char, 32>>()),
             kernel_sha = hex(r.get<std::array<unsigned char, 32>>()),
             source_fixture_sha = hex(r.get<std::array<unsigned char, 32>>());
  const auto heap_free_address = r.get<std::uint64_t>();
  check(game_sha == tm2020::recovered::executable_sha256 &&
            tm2020::live::file_sha256(argv[1]) == game_sha,
        "Unknown game build");
  wchar_t system[MAX_PATH]{};
  check(GetSystemDirectoryW(system, MAX_PATH) > 0,
        "Cannot locate system directory");
  check(tm2020::live::file_sha256(std::filesystem::path(system) /
                                  L"ntdll.dll") == nt_sha,
        "Different OS module build");
  check(tm2020::live::file_sha256(std::filesystem::path(system) /
                                  L"kernel32.dll") == kernel_sha,
        "Different kernel32 build");
  check(reinterpret_cast<std::uint64_t>(
            GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "HeapFree")) ==
            heap_free_address,
        "Platform import base changed");
  const auto base = r.get<std::uint64_t>(), ntbase = r.get<std::uint64_t>();
  check(reinterpret_cast<std::uint64_t>(GetModuleHandleW(L"ntdll.dll")) ==
            ntbase,
        "OS module base changed; recapture required");
  const auto image_size = r.get<std::uint32_t>(), nc = r.get<std::uint32_t>(),
             nd = r.get<std::uint32_t>(), no = r.get<std::uint32_t>();
  const auto manager = r.get<std::uint64_t>(), states = r.get<std::uint64_t>();
  const auto state_count = r.get<std::uint32_t>(),
             reference_ticks = r.get<std::uint32_t>();
  const auto ticks = reference_ticks;
  check(ticks > 0 && ticks <= 1000, "Reference horizon bound");
  const auto timing = r.get<std::array<std::uint32_t, 3>>();
  check(timing[1] == 10 && timing[2] == 0x3c23d70b &&
            timing[0] <= 0xffffffffu - (ticks - 1) * 10,
        "Unsupported original-step timing");
  std::uint64_t control_vehicle{};
  std::array<float, 4> controls{};
  std::vector<std::array<float, 3>> control_schedule;
  bool hold_controls{};
  bool hold_action_axis{};
  std::uint32_t steering_offset{0x1430};
  if (version >= 5) {
    control_vehicle = r.get<std::uint64_t>();
    const auto count = r.get<std::uint32_t>();
    check(count == ticks && count <= 1000, "Invalid control schedule horizon");
    if (version >= 6) {
      steering_offset = r.get<std::uint32_t>();
      check(steering_offset == 0xa0, "Invalid steering command offset");
    }
    control_schedule.resize(count);
    for (auto &row : control_schedule) {
      r.read(row.data(), sizeof(row));
      check(std::all_of(row.begin(), row.end(), [](float v) {
              return std::isfinite(v) && std::abs(v) <= 1.0f;
            }), "Scheduled internal control outside [-1, 1]");
    }
    check(control_vehicle >= 0x100000000ull && control_vehicle < 0x40000000000ull,
          "Invalid control schedule vehicle");
  } else if (version >= 4) {
    const auto flag = r.get<std::uint32_t>();
    control_vehicle = r.get<std::uint64_t>();
    controls = r.get<std::array<float, 4>>();
    check(flag <= 3, "Invalid control schedule flag");
    hold_controls = (flag & 1) != 0;
    hold_action_axis = (flag & 2) != 0;
    if (hold_controls || hold_action_axis)
      check(control_vehicle >= 0x100000000ull && control_vehicle < 0x40000000000ull &&
                std::all_of(controls.begin(), controls.begin() + 3, [](float v) { return std::isfinite(v) && std::abs(v) <= 1.0f; }) &&
                (!hold_action_axis || (std::isfinite(controls[3]) && std::abs(controls[3]) <= 1.0f)),
            "Invalid held control schedule");
  }
  unsigned pipeline_version{};
  std::uint64_t collision_world{},force_context{};
  if(version==7){
    pipeline_version=r.get<std::uint32_t>();
    check(pipeline_version>=1 && pipeline_version<=4,"Unsupported scene pipeline version");
    collision_world=r.get<std::uint64_t>();force_context=r.get<std::uint64_t>();
  }
  check(base >= 0x100000000ull && base < 0x7fff00000000ull &&
            base % 65536 == 0 && image_size < 128 * 1024 * 1024 &&
            image_size > 0x852000 && nc > 0 && nc < 2048 && nd > 0 &&
            nd < 4096 && no < 256 && state_count > 0 && state_count <= 64,
        "Invalid fixture extents");
  std::vector<std::uint32_t> code(nc);
  r.read(code.data(), nc * 4);
  std::map<std::uint32_t, std::vector<std::pair<unsigned, unsigned char>>>
      overlays;
  for (unsigned n = 0; n < no; ++n) {
    const auto page = r.get<std::uint32_t>(), count = r.get<std::uint32_t>();
    check(page % 4096 == 0 && count <= 4096, "Overlay extent");
    for (unsigned j = 0; j < count; ++j) {
      const auto offset = r.get<std::uint16_t>();
      const auto value = r.get<unsigned char>();
      check(offset < 4096, "Overlay offset");
      overlays[page].push_back({offset, value});
    }
  }
  std::vector<Data> data(nd);
  std::set<std::uint64_t> addresses;
  for (auto &p : data) {
    p.address = r.get<std::uint64_t>();
    r.read(p.initial.data(), 4096);
    check(p.address % 4096 == 0 && addresses.insert(p.address).second,
          "Duplicate/misaligned data");
    check((p.address >= base && p.address <= base + image_size - 4096) ||
              (p.address >= 0x100000000ull &&
               p.address <= 0x40000000000ull - 4096),
          "Data domain");
  }
  if (hold_controls || !control_schedule.empty()) {
    for (const auto offset : {0x98u, 0x9cu, steering_offset}) {
      const auto address = control_vehicle + offset;
      check(addresses.contains(address & ~std::uint64_t(4095)) &&
                addresses.contains((address + 3) & ~std::uint64_t(4095)),
            "Control override outside owned fixture pages");
    }
  }
  if(pipeline_version){
    for(const auto receiver:{collision_world,force_context})
      check(receiver>=0x100000000ull && receiver<0x40000000000ull
            &&addresses.contains(receiver&~std::uint64_t(4095)),
            "Scene pipeline receiver outside owned pages");
  }
  if (hold_action_axis) {
    const auto address = control_vehicle + 0x1374;
    check(addresses.contains(address & ~std::uint64_t(4095)) &&
              addresses.contains((address + 3) & ~std::uint64_t(4095)),
          "Action-axis override outside owned fixture pages");
  }
  const auto output_count = r.get<std::uint32_t>();
  check(output_count == 3, "Expected rigid, vehicle and force output records");
  std::vector<Output> outputs(output_count);
  for (auto &o : outputs) {
    o.address = r.get<std::uint64_t>();
    const auto count = r.get<std::uint32_t>();
    check(count > 0 && count < 1024 * 1024, "Output bytes bound");
    check(std::uint64_t(count) * ticks <= 16 * 1024 * 1024,
          "Reference byte extent");
    o.mask.resize(count);
    o.expected.resize(std::size_t(count) * ticks);
    r.read(o.mask.data(), count);
    r.read(o.expected.data(), o.expected.size());
    check(std::all_of(o.mask.begin(), o.mask.end(),
                      [](auto b) { return b <= 1; }),
          "Output mask");
  }
  check(outputs[0].address == states &&
            outputs[0].mask.size() == state_count * 88 &&
            std::all_of(outputs[0].mask.begin(), outputs[0].mask.end(),
                        [](auto byte) { return byte == 1; }) &&
            outputs[1].mask.size() == 0x1d00 && outputs[2].mask.size() == 24,
        "Unsupported typed reference layout");
  check(r.f.peek() == std::char_traits<char>::eof(), "Trailing fixture data");
  std::ifstream exe(argv[1], std::ios::binary);
  std::vector<char> raw((std::istreambuf_iterator<char>(exe)), {});
  IMAGE_DOS_HEADER dos{};
  check(raw.size() > sizeof(dos), "Short PE");
  std::memcpy(&dos, raw.data(), sizeof(dos));
  IMAGE_NT_HEADERS64 nt{};
  check(dos.e_magic == IMAGE_DOS_SIGNATURE && dos.e_lfanew > 0 &&
            std::size_t(dos.e_lfanew) + sizeof(nt) <= raw.size(),
        "Invalid PE");
  std::memcpy(&nt, raw.data() + dos.e_lfanew, sizeof(nt));
  check(nt.Signature == IMAGE_NT_SIGNATURE &&
            nt.OptionalHeader.SizeOfImage == image_size,
        "Wrong image size");
  const auto section_at = dos.e_lfanew + 4 + sizeof(IMAGE_FILE_HEADER) +
                          nt.FileHeader.SizeOfOptionalHeader;
  std::vector<IMAGE_SECTION_HEADER> sections;
  for (unsigned n = 0; n < nt.FileHeader.NumberOfSections; ++n) {
    IMAGE_SECTION_HEADER s{};
    check(section_at + (n + 1) * sizeof(s) <= raw.size(),
          "Truncated section table");
    std::memcpy(&s, raw.data() + section_at + n * sizeof(s), sizeof(s));
    sections.push_back(s);
  }
  std::set<std::uint32_t> code_set(code.begin(), code.end());
  for (const auto &section : sections)
    if (std::memcmp(section.Name, ".text", 5) == 0)
      for (std::uint32_t at = section.VirtualAddress;
           std::uint64_t(at) + 4096 <=
           std::uint64_t(section.VirtualAddress) + section.SizeOfRawData;
           at += 4096)
        code_set.insert(at);
  code.assign(code_set.begin(), code_set.end());
  Memory memory;
  memory.reserve(base, image_size);
  for (auto [a, size] : std::array<std::pair<std::uint64_t, std::size_t>, 3>{
           {{0x600000000ull, 0x1000000},
            {0x700000000ull, 0x4000000},
            {0x800000000ull, 0x4000000}}}) {
    memory.reserve(a, size);
    memory.commit(a, size);
  }
  std::set<std::uint64_t> heap_groups;
  for (const auto &p : data)
    if (!(base <= p.address && p.address < base + image_size) &&
        !(0x600000000ull <= p.address && p.address < 0x601000000ull) &&
        !(0x700000000ull <= p.address && p.address < 0x704000000ull) &&
        !(0x800000000ull <= p.address && p.address < 0x804000000ull))
      heap_groups.insert(p.address & ~std::uint64_t(65535));
  for (auto a : heap_groups)
    memory.reserve(a, 65536);
  for (const auto &p : data) {
    memory.commit(p.address);
    std::memcpy(reinterpret_cast<void *>(p.address), p.initial.data(), 4096);
  }
  for (auto page : code) {
    check(page % 4096 == 0 && std::uint64_t(page) + 4096 <= image_size &&
              addresses.insert(base + page).second,
          "Code/data collision");
    auto s = std::find_if(sections.begin(), sections.end(), [&](const auto &s) {
      return (s.Characteristics & IMAGE_SCN_MEM_EXECUTE) &&
             s.VirtualAddress <= page &&
             std::uint64_t(page) + 4096 <=
                 std::uint64_t(s.VirtualAddress) + s.SizeOfRawData;
    });
    check(s != sections.end(), "Code outside executable section");
    const auto off =
        std::uint64_t(s->PointerToRawData) + page - s->VirtualAddress;
    check(off + 4096 <= raw.size(), "Code beyond file");
    memory.commit(base + page);
    std::memcpy(reinterpret_cast<void *>(base + page), raw.data() + off, 4096);
    for (auto [offset, value] : overlays[page])
      *reinterpret_cast<unsigned char *>(base + page + offset) = value;
    DWORD old{};
    check(VirtualProtect(reinterpret_cast<void *>(base + page), 4096,
                         PAGE_EXECUTE_READ, &old) != 0,
          "Cannot protect owned code");
  }
  for (const auto &o : outputs)
    for (std::size_t i = 0; i < o.mask.size(); ++i)
      if (o.mask[i])
        check(addresses.contains((o.address + i) & ~std::uint64_t(4095)),
              "Observed output outside owned pages");
  for (const auto &[page, changes] : overlays)
    check(std::find(code.begin(), code.end(), page) != code.end(),
          "Overlay outside code pages");
  check(addresses.contains(manager & ~std::uint64_t(4095)) &&
            addresses.contains(states & ~std::uint64_t(4095)),
        "Manager/state outside owned fixture");
  check(std::find(code.begin(), code.end(), 0x7bd000) != code.end(),
        "Main entry missing");
  FlushInstructionCache(GetCurrentProcess(), reinterpret_cast<void *>(base),
                        image_size);
  struct Heap {
    HANDLE handle{HeapCreate(0, 0, 0)};
    ~Heap() {
      if (handle)
        HeapDestroy(handle);
    }
  } heap;
  check(heap.handle != nullptr, "Cannot create owned platform heap");
  const bool heap_binding_present =
      addresses.contains((base + 0x1f84208) & ~std::uint64_t(4095));
  if (heap_binding_present)
    std::memcpy(reinterpret_cast<void *>(base + 0x1f84208), &heap.handle,
                sizeof(heap.handle));

  const auto module = GetModuleHandleW(L"ntdll.dll");
  const std::array<const char *, 4> names{
      "RtlAllocateHeap", "RtlReAllocateHeap", "RtlFreeHeap", "RtlSizeHeap"};
  for (unsigned n = 0; n < 4; ++n) {
    api[n] = reinterpret_cast<std::uint64_t>(GetProcAddress(module, names[n]));
    check(api[n] != 0, "Missing platform API");
  }
  auto diagnostic = AddVectoredExceptionHandler(1, fault);
  check(diagnostic != nullptr, "Cannot add diagnostic");
  SimulationJob job{base,  manager,         states,  timing,
                    ticks, reference_ticks, &outputs, control_vehicle,
                    controls, hold_controls, hold_action_axis,
                    std::move(control_schedule), steering_offset};
  job.initial_pages=&data;job.episodes=episodes;
  job.pipelineVersion=pipeline_version;job.collisionWorld=collision_world;
  job.registeredForceContext=force_context;
  job.heap_binding=heap_binding_present?base+0x1f84208:0;
  job.heap_handle=reinterpret_cast<std::uint64_t>(heap.handle);
  HANDLE worker = CreateThread(nullptr, 0, simulate, &job, CREATE_SUSPENDED,
                               &simulation_thread);
  check(worker != nullptr, "Cannot create owned simulation thread");
  CONTEXT context{};
  context.ContextFlags = CONTEXT_DEBUG_REGISTERS;
  check(GetThreadContext(worker, &context) != 0,
        "Cannot read owned thread context");
  context.Dr0 = api[0];
  context.Dr1 = api[1];
  context.Dr2 = api[2];
  context.Dr3 = api[3];
  context.Dr6 = 0;
  context.Dr7 = 0x55;
  check(SetThreadContext(worker, &context) != 0,
        "Cannot bind owned platform ABI breakpoints");
  check(ResumeThread(worker) != DWORD(-1),
        "Cannot start owned simulation thread");
  const auto timeout=std::max<DWORD>(30000,std::min<DWORD>(300000,episodes*100));
  if(WaitForSingleObject(worker,timeout)!=WAIT_OBJECT_0){
    std::cerr<<"Owned simulation timeout; terminating the owned helper process\n";
    ExitProcess(25);
  }
  DWORD status{};
  check(GetExitCodeThread(worker, &status) != 0 && status == 0,
        "Owned simulation failed");
  CloseHandle(worker);
  RemoveVectoredExceptionHandler(diagnostic);
  check(job.firstExact && job.framesCompared == reference_ticks && job.episodesCompared==episodes,
        "Complete reference trace was not verified");
  std::cout << "PASS NATIVE_CHAIN ticks=" << ticks
            << " retained_horizon_observed_physics_bit_exact=true "
               "game_process_access=false"
            << std::endl;

  std::ofstream report(argv[3]);
  check(bool(report), "Cannot create original-step report");
  std::size_t observed{};
  for (const auto &o : outputs)
    for (auto byte : o.mask)
      observed += byte;
  report
      << "{\n  \"schema\": \"tm2020_native_original_step_v1\",\n  \"sha256\": "
         "\""
      << game_sha << "\",\n  \"ntdllSha256\": \"" << nt_sha
      << "\",\n  \"kernel32Sha256\": \"" << kernel_sha
      << "\",\n  \"sourceFixtureSha256\": \"" << source_fixture_sha
      << "\",\n  \"nativeFixtureSha256\": \""
      << tm2020::live::file_sha256(argv[2])
      << "\",\n  \"referenceFrames\": " << reference_ticks
      << ",\n  \"typedFramesCompared\": " << job.framesCompared
      << ",\n  \"nativeFixtureVersion\": " << version
      << ",\n  \"selectedScenePipelineVersion\": " << pipeline_version
      << ",\n  \"steeringOverrideOffset\": " << steering_offset
      << ",\n  \"scheduledControlFrames\": " << job.control_schedule.size()
      << ",\n  \"resetEpisodesCompared\": " << job.episodesCompared
      << ",\n  \"totalTypedFramesCompared\": " << job.totalFramesCompared
      << ",\n  \"snapshotDataPagesRestoredPerReset\": " << data.size()
      << ",\n  \"syntheticArenaBytesClearedPerReset\": " << 0x9000000
      << ",\n  \"observedBytesPerFrame\": " << observed
      << ",\n  \"rigidStateBytesPerFrame\": " << state_count * 88
      << ",\n  \"elapsedSecondsIncludingComparisonAndProgressOutput\": "
      << job.elapsedSeconds
      << ",\n  \"stepsPerSecondIncludingComparisonAndProgressOutput\": "
      << job.totalFramesCompared / job.elapsedSeconds
      << ",\n  \"allTypedPhysicalFramesBitExact\": true,\n  "
         "\"completeMainProcedureReturnedEveryFrame\": true,\n  "
         "\"originalGameInstructionsModified\": false,\n  "
         "\"gameProcessAccessed\": false,\n  "
         "\"platformAbiBoundOnOwnedThread\": true,\n  "
         "\"originalExecutableRequired\": true,\n  "
         "\"sameOsModuleCohortRequired\": true,\n  \"runtimePythonRequired\": "
         "false,\n  \"wholeStepInstructionOracleQualified\": false,\n  "
         "\"constructedTlsResetEveryEpisode\": true,\n  "
         "\"ownedAllocatorResetEveryEpisode\": true,\n  "
         "\"generalSnapshotRewindQualified\": false,\n  "
         "\"fullHeadlessSimulatorQualified\": false\n}\n";
  check(bool(report), "Cannot write original-step report");

} catch (const std::exception &e) {
  std::cerr << e.what() << '\n';
  return 1;
}

#include "tm2020/recovered_position.hpp"
#include "owned_arithmetic_image.hpp"
#include <intrin.h>
#include <iostream>
#include <random>
using namespace tm2020::recovered;using namespace tm2020::testing;
// Loader-owned TLS template in this TEST executable. The original profiler
// reads TLS module zero +0x1b8. No TEB/GS/code patching or live-game access.
#if defined(_MSC_VER)
#pragma section(".tls$BBB",read,write)
__declspec(allocate(".tls$BBB")) unsigned char owned_profiler_template[0x4000]{};
#else
__attribute__((section(".tls$BBB"),used)) unsigned char owned_profiler_template[0x4000]{};
#endif
struct Case {std::array<RigidState,3> states;std::array<VelocityCoefficients,3> coefficients;PositionParameters parameters;std::array<DynamicPositionConstraint,2> dynamic;std::array<StaticPositionConstraint,2> fixed;std::uint32_t count;};
static_assert(sizeof(Case)==496);
template<class T>struct Span {const T* data{};std::uint32_t count{},pad{};};
int main(int argc,char** argv)try{
 check(argc==4,"Usage: position_fma_oracle original.exe position-input.bin report.json");
#if defined(_MSC_VER)
 int cpu[4]{};__cpuid(cpu,1);check((cpu[2]&(1<<12))!=0&&(GetEnabledXStateFeatures()&6)==6,"Native original FMA oracle requires enabled AVX/FMA CPU");
#else
 check(__builtin_cpu_supports("fma"),"Native original FMA oracle requires FMA CPU");
#endif
 const auto* main=reinterpret_cast<const unsigned char*>(GetModuleHandleW(nullptr));const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(main);const auto* nt=reinterpret_cast<const IMAGE_NT_HEADERS64*>(main+dos->e_lfanew);const auto& dir=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS];check(dir.VirtualAddress&&dir.Size>=sizeof(IMAGE_TLS_DIRECTORY64),"Owned fixture lacks native TLS directory");const auto* tls=reinterpret_cast<const IMAGE_TLS_DIRECTORY64*>(main+dir.VirtualAddress);check(tls->EndAddressOfRawData-tls->StartAddressOfRawData>=0x1c0,"Owned TLS template too short");check(*reinterpret_cast<const DWORD*>(tls->AddressOfIndex)==0,"Owned test executable is not TLS module zero");const auto* table=reinterpret_cast<const std::uintptr_t*>(__readgsqword(0x58));check(table&&table[0]&&*reinterpret_cast<const std::uintptr_t*>(table[0]+0x1b8)==0,"Original profiler's ordinary null branch is not available");
 const std::array<std::array<unsigned,2>,7> ranges{{{0x85e4f0,0x85eab0},{0x8603b0,0x860d55},{0x192c70,0x192cd7},{0x195c010,0x195c50f},{0x195d240,0x195d936},{0x1886d0,0x188800},{0x1175b0,0x117763}}};ArithmeticImage image(argv[1],ranges);DWORD prior{};check(VirtualProtect(image.base+0x1f84000,0x1000,PAGE_READWRITE,&prior)!=0,"Cannot set private math-dispatch data");const std::uint32_t flag=1;std::memcpy(image.base+0x1f840e4,&flag,4);
 using Rotate=void(*)(void*,const void*);const auto positive=reinterpret_cast<Rotate>(image.base+0x85e4f0),negative=reinterpret_cast<Rotate>(image.base+0x85e7d0);
 std::mt19937_64 rng(0x2026102402);std::uniform_real_distribution<float> u(-1,1);for(std::size_t n=0;n<20000;n++){RigidState s;for(float& x:s.quaternion)x=u(rng);for(float& x:s.rotation)x=u(rng);std::array<float,3> correction{u(rng)*.8f,u(rng)*.8f,u(rng)*.8f};if(n%5==0)for(float& x:correction)x=x*1e-6f;if(n%7==0)correction={-0.f,0,0};if(n%11==0)s.quaternion={};if(n%13==0)for(float& x:s.quaternion)x=x*1e6f;if(n%17==0)for(float& x:s.quaternion)x=x*1e-20f;if(n%19==0)correction={1.57079625f,0,0};if(n%23==0)correction={std::ldexp(1.f,-12),0,0};if(n%29==0)correction={std::ldexp(1.f,-6),0,0};for(unsigned sign=0;sign<2;sign++){auto original=s,ported=s;(sign?negative:positive)(&original,&correction);correct_rotation(ported,correction,sign!=0,PositionMathPath::fused_avx_fma);check(std::memcmp(&original,&ported,sizeof(s))==0,"FMA rotation mismatch");}}
 std::ifstream inputs(argv[2],std::ios::binary);check(bool(inputs),"Cannot read position cases");std::uint32_t count{};inputs.read(reinterpret_cast<char*>(&count),4);check(count==20000,"Expected qualified 20,000-case sweep input");using Sweep=void(*)(const void*,void*,void*,const void*,const void*);const auto dynamic=reinterpret_cast<Sweep>(image.base+0x8603b0),fixed=reinterpret_cast<Sweep>(image.base+0x860980);
 for(std::uint32_t n=0;n<count;n++){Case c;inputs.read(reinterpret_cast<char*>(&c),sizeof(c));check(bool(inputs),"Truncated position cases");std::array<std::byte,32> config{};std::memcpy(config.data()+20,&c.parameters,12);const Span<DynamicPositionConstraint> ds{c.dynamic.data(),c.count};const Span<StaticPositionConstraint> ss{c.fixed.data(),c.count};for(unsigned which=0;which<2;which++){auto native=c.states,ported=c.states;if(which){fixed(c.coefficients.data(),native.data(),nullptr,&ss,config.data());solve_static_positions(ported,c.coefficients,std::span(c.fixed.data(),c.count),c.parameters,PositionMathPath::fused_avx_fma);}else{dynamic(c.coefficients.data(),native.data(),nullptr,&ds,config.data());solve_dynamic_positions(ported,c.coefficients,std::span(c.dynamic.data(),c.count),c.parameters,PositionMathPath::fused_avx_fma);}if(std::memcmp(native.data(),ported.data(),sizeof(native))){std::cerr<<"MISMATCH case="<<n<<" sweep="<<which<<'\n';throw std::runtime_error("Native complete FMA position sweep differs");}}}
 std::ofstream report(argv[3]);report<<"{\"schema\":\"tm2020_position_fma_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_sign_and_sweep\":20000,\"rotation_signs\":2,\"complete_position_sweeps\":2,\"bit_exact\":true,\"original_instructions_native\":true,\"originalCodeModified\":false,\"functionsSkipped\":false,\"loader_owned_profiler_tls_null_branch\":true,\"math_dispatch_flag\":1,\"maximum_correction_norm\":1.57079625,\"larger_angle_reduction_qualified\":false,\"whole_original_fma_position_island_loop_qualified\":false,\"game_process_accessed\":false}\n";report.flush();check(bool(report),"Cannot write FMA proof");
 std::cout<<"PASS FMA_POSITION_ORACLE rotation_signs=2 position_sweeps=2 cases_each=20000 bit_exact=true original_profiler_tls=true no_functions_skipped=true\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

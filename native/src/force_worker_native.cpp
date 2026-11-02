#include "tm2020/recovered_rigid.hpp"
#include "force_worker_fixture.hpp"
#include "tm2020/read_only_live.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <intrin.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <vector>
#if defined(_MSC_VER)
#pragma section(".tls$BBB",read,write)
__declspec(allocate(".tls$BBB")) unsigned char owned_force_profiler_tls[0x4000]{};
#else
__attribute__((section(".tls$BBB"),used)) unsigned char owned_force_profiler_tls[0x4000]{};
#endif
void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
struct Reservations{std::vector<void*> p;~Reservations(){for(auto q:p)VirtualFree(q,0,MEM_RELEASE);}void reserve(std::uintptr_t address,std::size_t size){auto q=VirtualAlloc(reinterpret_cast<void*>(address),size,MEM_RESERVE,PAGE_NOACCESS);check(q==reinterpret_cast<void*>(address),"Requested owned address range unavailable");p.push_back(q);}void commit(std::uintptr_t address){check(VirtualAlloc(reinterpret_cast<void*>(address),4096,MEM_COMMIT,PAGE_READWRITE)==reinterpret_cast<void*>(address),"Cannot commit owned fixture page");}};
LONG CALLBACK owned_fault(EXCEPTION_POINTERS* info){std::cerr<<"OWNED_NATIVE_EXCEPTION code=0x"<<std::hex<<info->ExceptionRecord->ExceptionCode<<" rip=0x"<<info->ContextRecord->Rip<<std::dec<<'\n';ExitProcess(23);return EXCEPTION_CONTINUE_SEARCH;}
int main(int argc,char**argv)try{
 check(argc==5,"Usage: tm2020_force_worker_native original.exe fixture.tmforce repeats report.json");check(tm2020::live::file_sha256(argv[1])==tm2020::recovered::executable_sha256,"Unknown original build");const auto repeats=std::stoul(argv[3]);check(repeats>0&&repeats<=100000,"Invalid repeat bound");
 std::ifstream source(argv[1],std::ios::binary);std::vector<char> raw((std::istreambuf_iterator<char>(source)),{});IMAGE_DOS_HEADER dos{};check(raw.size()>sizeof(dos),"Short PE");std::memcpy(&dos,raw.data(),sizeof(dos));IMAGE_NT_HEADERS64 nt{};check(dos.e_magic==IMAGE_DOS_SIGNATURE&&dos.e_lfanew>0&&std::size_t(dos.e_lfanew)+sizeof(nt)<=raw.size(),"Invalid DOS header");std::memcpy(&nt,raw.data()+dos.e_lfanew,sizeof(nt));check(nt.Signature==IMAGE_NT_SIGNATURE&&nt.FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64&&nt.OptionalHeader.SizeOfImage<128*1024*1024,"Invalid original PE");
 std::vector<IMAGE_SECTION_HEADER> sections;const auto table=dos.e_lfanew+4+sizeof(IMAGE_FILE_HEADER)+nt.FileHeader.SizeOfOptionalHeader;for(unsigned n=0;n<nt.FileHeader.NumberOfSections;n++){IMAGE_SECTION_HEADER s{};check(table+(n+1)*sizeof(s)<=raw.size(),"Invalid section table");std::memcpy(&s,raw.data()+table+n*sizeof(s),sizeof(s));sections.push_back(s);}
 const auto fixture=tm2020::research::read_force_fixture(argv[2],std::string(tm2020::recovered::executable_sha256));
 const auto base=fixture.base;const auto image_size=fixture.imageSize;const auto&code_pages=fixture.codePages;const auto&data=fixture.dataPages;const auto timestamp=fixture.timestamp;const auto float_bits=fixture.intervalBits,mxcsr=fixture.mxcsr;const auto r9=fixture.r9;alignas(16)auto context=fixture.context;
 check(image_size==nt.OptionalHeader.SizeOfImage,"Fixture/original PE extent differs");
 const auto fixture_hash=tm2020::live::file_sha256(argv[2]);std::set<std::uintptr_t> seen;for(const auto&p:data)seen.insert(p.address);
 Reservations memory;memory.reserve(base,image_size);std::set<std::uintptr_t> heap_groups;
 for(const auto&p:data)if(!(base<=p.address&&p.address<base+image_size)){check(p.address>=0x100000000ull&&p.address<0x40000000000ull,"Heap fixture address exceeds owned domain");heap_groups.insert(p.address&~std::uintptr_t(65535));}
 for(auto group:heap_groups)memory.reserve(group,65536);
 for(const auto&p:data){memory.commit(p.address);std::memcpy(reinterpret_cast<void*>(p.address),p.initial.data(),4096);}
 for(auto page:code_pages){check((page&4095)==0&&page<image_size&&seen.insert(base+page).second,"Invalid/duplicate code page");const auto s=std::find_if(sections.begin(),sections.end(),[&](const auto& v){return page>=v.VirtualAddress&&std::uint64_t(page)+4096<=std::uint64_t(v.VirtualAddress)+v.SizeOfRawData;});check(s!=sections.end()&&std::memcmp(s->Name,".text",5)==0,"Code page outside ordinary .text");const auto at=std::uint64_t(s->PointerToRawData)+(page-s->VirtualAddress);check(at+4096<=raw.size(),"Code page beyond PE");memory.commit(base+page);std::memcpy(reinterpret_cast<void*>(base+page),raw.data()+at,4096);DWORD old{};check(VirtualProtect(reinterpret_cast<void*>(base+page),4096,PAGE_EXECUTE_READ,&old)!=0,"Cannot protect owned code page");}
 // Check the loader's own TLS template before entering the original profiler.
 // These reads do not alter the TEB, GS base, or any original instruction.
 const auto* main=reinterpret_cast<const unsigned char*>(GetModuleHandleW(nullptr));
 const auto* main_dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(main);
 const auto* main_nt=reinterpret_cast<const IMAGE_NT_HEADERS64*>(main+main_dos->e_lfanew);
 const auto& tls_directory=main_nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS];
 check(tls_directory.VirtualAddress && tls_directory.Size>=sizeof(IMAGE_TLS_DIRECTORY64),"Owned runner lacks loader TLS");
 const auto* tls=reinterpret_cast<const IMAGE_TLS_DIRECTORY64*>(main+tls_directory.VirtualAddress);
 check(tls->EndAddressOfRawData-tls->StartAddressOfRawData>=0x1c0 && *reinterpret_cast<const DWORD*>(tls->AddressOfIndex)==0,"Owned runner is not TLS module zero");
 const auto* tls_table=reinterpret_cast<const std::uintptr_t*>(__readgsqword(0x58));
 check(tls_table && tls_table[0] && *reinterpret_cast<const std::uintptr_t*>(tls_table[0]+0x1b8)==0,"Original profiler null branch unavailable");
 FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(base),image_size);
 struct FloatingPointEnvironment {unsigned saved{_mm_getcsr()};~FloatingPointEnvironment(){_mm_setcsr(saved);}} floating_point_environment;
 _mm_setcsr(mxcsr);
 struct FaultDiagnostic {void* handle{AddVectoredExceptionHandler(1,owned_fault)};~FaultDiagnostic(){if(handle)RemoveVectoredExceptionHandler(handle);}} diagnostic;
 check(diagnostic.handle!=nullptr,"Cannot add owned fault diagnostic");
 using Fn=void(*)(std::uint64_t,float,const void*,std::uint64_t);const auto worker=reinterpret_cast<Fn>(base+0x851f00);float blend{};std::memcpy(&blend,&float_bits,4);const auto started=std::chrono::steady_clock::now();
 for(unsigned long n=0;n<repeats;n++){
  for(const auto&p:data)std::memcpy(reinterpret_cast<void*>(p.address),p.initial.data(),4096);
  worker(timestamp,blend,context.data(),r9);
  for(const auto&p:data)if(std::memcmp(reinterpret_cast<const void*>(p.address),p.expected.data(),4096)){const auto* a=reinterpret_cast<const unsigned char*>(p.address);for(unsigned j=0;j<4096;j++)if(a[j]!=p.expected[j]){std::cerr<<"OUTPUT_MISMATCH iteration="<<n<<" address=0x"<<std::hex<<p.address+j<<std::dec<<" native="<<unsigned(a[j])<<" expected="<<unsigned(p.expected[j])<<'\n';break;}throw std::runtime_error("Complete native worker differs from offline emulation");}
 }
 const auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();std::cout<<"PASS COMPLETE_NATIVE_FORCE_WORKER entry=0x851f00 repeats="<<repeats<<" all_data_pages_bit_exact=true game_process_access=false original_code_modified=false functions_skipped=false elapsed_s="<<seconds<<" calls_per_second="<<repeats/seconds<<'\n';
 std::size_t retained{};for(const auto&p:data)for(auto b:p.mask)retained+=b;
 std::ofstream report(argv[4]);check(bool(report),"Cannot create force worker report");
 report<<"{\n  \"schema\": \"tm2020_native_force_worker_v2\",\n  \"sha256\": \""<<tm2020::recovered::executable_sha256<<"\",\n"
       <<"  \"fixtureSha256\": \""<<fixture_hash<<"\",\n  \"entryRva\": \"0x851f00\",\n"
       <<"  \"repetitions\": "<<repeats<<",\n  \"independentInputCases\": 1,\n  \"codePages\": "<<code_pages.size()<<",\n  \"dataPages\": "<<data.size()<<",\n  \"retainedDataBytes\": "<<retained<<",\n"
       <<"  \"allDataPagesBitExact\": true,\n  \"completeWorkerReturned\": true,\n  \"gameProcessAccessed\": false,\n  \"originalCodeModified\": false,\n  \"functionsSkipped\": false,\n  \"originalExecutableRequired\": true,\n  \"runtimePythonRequired\": false,\n  \"wholeGameStepQualified\": false,\n  \"elapsedSeconds\": "<<seconds<<",\n  \"callsPerSecondIncludingRestoreAndComparison\": "<<repeats/seconds<<"\n}\n";
 check(bool(report),"Cannot write force worker report");
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}

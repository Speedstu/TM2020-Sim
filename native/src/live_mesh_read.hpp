#pragma once
#include "tm2020/read_only_live.hpp"
#include "tm2020/recovered_mesh.hpp"
#include "tm2020/recovered_rigid.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
using namespace tm2020::recovered;
struct Reader {HANDLE h{};~Reader(){if(h)CloseHandle(h);}template<class T>bool get(std::uintptr_t a,T& v){SIZE_T n{};return a>=0x10000&&ReadProcessMemory(h,reinterpret_cast<void*>(a),&v,sizeof(v),&n)&&n==sizeof(v);}};
inline void verify_pinned_build(Reader& p){std::array<wchar_t,32768> path{};DWORD size=std::uint32_t(path.size());if(!QueryFullProcessImageNameW(p.h,0,path.data(),&size)||tm2020::live::file_sha256(std::filesystem::path(std::wstring(path.data(),size)))!=executable_sha256)throw std::runtime_error("Unknown game build for typed mesh layouts");}
struct Span {std::uintptr_t pointer{};std::uint32_t count{},opaque{};};
struct Mesh {std::uint64_t opaque0{};std::uint32_t opaque8{},type{};std::array<std::byte,16> opaque10{};Span vertices,raw_triangles,cooked_triangles,tree;};static_assert(sizeof(Mesh)==96);
template<class F>std::uint64_t scan(Reader& p,std::uint64_t max_mb,F f){const std::size_t block=1<<20,overlap=128;std::vector<std::byte> bytes(block+overlap);std::uintptr_t address=0x10000;std::uint64_t scanned{};MEMORY_BASIC_INFORMATION region{};while(VirtualQueryEx(p.h,reinterpret_cast<void*>(address),&region,sizeof(region))==sizeof(region)){const auto base=reinterpret_cast<std::uintptr_t>(region.BaseAddress),end=base+region.RegionSize;if(end<=address)break;address=end;const auto prot=region.Protect&255;if(region.State!=MEM_COMMIT||region.Type!=MEM_PRIVATE||(region.Protect&(PAGE_GUARD|PAGE_NOACCESS))||(prot!=PAGE_READWRITE&&prot!=PAGE_WRITECOPY&&prot!=PAGE_EXECUTE_READWRITE&&prot!=PAGE_EXECUTE_WRITECOPY))continue;for(auto at=base;at<end&&scanned<max_mb*1048576;){const auto n=std::min<std::uint64_t>({bytes.size(),end-at,max_mb*1048576-scanned});SIZE_T got{};if(ReadProcessMemory(p.h,reinterpret_cast<void*>(at),bytes.data(),n,&got))f(at,std::span(bytes.data(),got));scanned+=n;at+=n>overlap?n-overlap:n;}if(scanned>=max_mb*1048576)break;}return scanned;}
bool pointer(std::uintptr_t p){return p>0x10000&&p<0x7fffffff0000ull&&(p&3)==0;}
template<std::size_t N>bool finite(const std::array<float,N>& x){for(float f:x)if(!std::isfinite(f)||std::abs(f)>1e6)return false;return true;}

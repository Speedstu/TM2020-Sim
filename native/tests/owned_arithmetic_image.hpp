#pragma once
#include "tm2020/recovered_rigid.hpp"
#include "tm2020/read_only_live.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
namespace tm2020::testing {
using tm2020::recovered::executable_sha256;
inline void check(bool b,const char* text){if(!b)throw std::runtime_error(text);}
struct ArithmeticImage {
    std::byte* base{};
    ~ArithmeticImage(){if(base)VirtualFree(base,0,MEM_RELEASE);}
    explicit ArithmeticImage(const std::filesystem::path& file,std::span<const std::array<unsigned,2>> ranges){
        check(tm2020::live::file_sha256(file)==executable_sha256,"Original executable SHA mismatch");
        std::ifstream in(file,std::ios::binary);std::vector<char> raw((std::istreambuf_iterator<char>(in)),{});
        check(raw.size()>sizeof(IMAGE_DOS_HEADER),"Short PE input");
        IMAGE_DOS_HEADER dos{};std::memcpy(&dos,raw.data(),sizeof(dos));
        check(dos.e_magic==IMAGE_DOS_SIGNATURE&&dos.e_lfanew>0&&std::size_t(dos.e_lfanew)+sizeof(IMAGE_NT_HEADERS64)<raw.size(),"Invalid DOS header");
        IMAGE_NT_HEADERS64 nt{};std::memcpy(&nt,raw.data()+dos.e_lfanew,sizeof(nt));
        check(nt.Signature==IMAGE_NT_SIGNATURE&&nt.FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64&&
            nt.OptionalHeader.Magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC&&nt.OptionalHeader.SizeOfImage<128*1024*1024,"Invalid x64 image");
        const auto size=nt.OptionalHeader.SizeOfImage;
        base=static_cast<std::byte*>(VirtualAlloc(nullptr,size,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        check(base!=nullptr,"Cannot allocate owned arithmetic image");
        struct FailedConstruction {std::byte* allocation;bool complete{};~FailedConstruction(){if(!complete)VirtualFree(allocation,0,MEM_RELEASE);}} guard{base};
        const std::size_t table=dos.e_lfanew+4+sizeof(IMAGE_FILE_HEADER)+nt.FileHeader.SizeOfOptionalHeader;
        for(unsigned j=0;j<nt.FileHeader.NumberOfSections;j++){
            const auto at=table+j*sizeof(IMAGE_SECTION_HEADER);check(at+sizeof(IMAGE_SECTION_HEADER)<=raw.size(),"Invalid section table");
            IMAGE_SECTION_HEADER section{};std::memcpy(&section,raw.data()+at,sizeof(section));
            check(std::uint64_t(section.PointerToRawData)+section.SizeOfRawData<=raw.size()&&
                std::uint64_t(section.VirtualAddress)+section.SizeOfRawData<=size,"Invalid section range");
            std::memcpy(base+section.VirtualAddress,raw.data()+section.PointerToRawData,section.SizeOfRawData);
        }
        DWORD previous{};check(VirtualProtect(base,size,PAGE_READONLY,&previous)!=0,"Cannot protect owned data image");
        for(const auto range:ranges)
            check(VirtualProtect(base+range[0],range[1]-range[0],PAGE_EXECUTE_READ,&previous)!=0,"Cannot enable selected arithmetic routine");
        FlushInstructionCache(GetCurrentProcess(),base,size);
        guard.complete=true;
    }
};
}

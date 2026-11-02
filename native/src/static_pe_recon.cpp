// Offline static PE recon of the INSTALLED Trackmania.exe, read-only.
// Extract class-name/string candidates, RIP-relative cross-references,
// PE version/section metadata. Never launches/patches the game, never uses
// WriteProcessMemory or disables anti-cheat. Xrefs are CANDIDATES only;
// an x86-64 disassembler must confirm instruction boundaries.
#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
struct Section {std::string name;uint32_t rva,vsize,off,raw;bool executable;};
static uint16_t read16(const std::vector<uint8_t>& b,size_t p){
    if(p+2>b.size())throw std::runtime_error("Truncated PE u16");
    return uint16_t(b[p])|uint16_t(b[p+1])<<8;
}
static uint32_t read32(const std::vector<uint8_t>& b,size_t p){
    if(p+4>b.size())throw std::runtime_error("Truncated PE u32");
    uint32_t v=0;for(int k=0;k<4;k++)v|=uint32_t(b[p+k])<<(k*8);return v;
}
static uint64_t read64(const std::vector<uint8_t>& b,size_t p){
    return uint64_t(read32(b,p))|(uint64_t(read32(b,p+4))<<32);
}
static std::string escape(std::string s){
    std::ostringstream o;
    for(char c:s){
        if(c=='"'||c=='\\'){o<<'\\'<<c;}
        else if(static_cast<unsigned char>(c)<32)o<<' ';
        else o<<c;
    }
    return o.str();
}
static std::string hex(uint64_t value) {
    std::ostringstream s;s<<"0x"<<std::hex<<value;return s.str();
}
int main(int argc,char**argv)try{
    if(argc!=3){std::cerr<<"Usage: tm2020_pe_recon <D:\\...\\Trackmania.exe> <H:\\...\\report.json>\n";return 2;}
    const fs::path src=argv[1],dest=argv[2];
    if(!fs::is_regular_file(src))throw std::runtime_error("Input exe not found");
    const auto filelen=fs::file_size(src);
    if(filelen<1024||filelen>300ull*1024*1024)throw std::runtime_error("PE size outside research limits");
    std::ifstream f(src,std::ios::binary);
    std::vector<uint8_t> b((std::istreambuf_iterator<char>(f)),{});
    if(read16(b,0)!=0x5a4d)throw std::runtime_error("Bad DOS signature");
    auto pe=read32(b,0x3c);
    if(read32(b,pe)!=0x4550)throw std::runtime_error("Bad PE signature");
    const auto sections=read16(b,pe+6);
    const auto optional_size=read16(b,pe+20);
    const auto opt=pe+24;
    if(read16(b,opt)!=0x20b)throw std::runtime_error("Expected x64 PE32+");
    if(sections==0||sections>96||optional_size<112)throw std::runtime_error("Invalid sections/optional header");
    const uint64_t imagebase=read64(b,opt+24);
    const size_t secbase=opt+optional_size;
    std::vector<Section> list;
    for(unsigned i=0;i<sections;i++){
        const size_t a=secbase+i*40;
        if(a+40>b.size())throw std::runtime_error("Truncated section table");
        std::string name;
        for(int j=0;j<8&&b[a+j];j++)name.push_back((char)b[a+j]);
        const uint32_t size=read32(b,a+16),off=read32(b,a+20);
        if(off>b.size()||size>b.size()-off)throw std::runtime_error("Invalid section file bounds");
        list.push_back({name,read32(b,a+12),read32(b,a+8),off,size,(read32(b,a+36)&0x20000000u)!=0});
    }
    const auto raw2rva=[&](uint32_t off)->uint32_t{
        for(const auto& s:list)if(off>=s.off&&off-s.off<s.raw)return s.rva+(off-s.off);
        return 0;
    };
    // Scan executable code once for instruction-like RIP-relative xrefs.
    // This is a best-effort pattern recognizer, not instruction disassembly.
    std::multimap<uint32_t,uint32_t> rip_xrefs;
    for(const auto& s:list)if(s.executable && s.raw>=7) {
        for(uint32_t i=0;i+7<s.raw;i++){
            const uint8_t rex=b[s.off+i];
            const uint8_t op=b[s.off+i+1];
            const uint8_t mr=b[s.off+i+2];
            if(rex<0x48||rex>0x4f)continue;
            if(op!=0x8d && op!=0x8b && op!=0x89)continue;
            if((mr&0xc7)!=0x05)continue;
            const uint32_t disp=read32(b,s.off+i+3);
            const uint32_t dest_rva=(uint32_t)(s.rva+i+7+(int32_t)disp);
            rip_xrefs.emplace(dest_rva,s.rva+i);
        }
    }
    const std::vector<std::string> terms={
        "CSceneVehicleVis","CSceneVehiclePhy","CGameCtnCar","ReactorBoost",
        "Suspension","VehicleVis","VehicleState","Turbo","Ice","Asphalt",
        "Surface","Physics","CPlugVehicle","GroundContact","InputSteer",
        "Trackmania","Gbx"
    };
    fs::create_directories(dest.parent_path());
    std::ofstream out(dest,std::ios::binary);
    if(!out)throw std::runtime_error("Cannot write research report to H:");
    out<<"{\n \"schema\":\"tm2020_static_pe_vehicle_recon_v1\",\n";
    out<<" \"readOnly\":true,\"source\":\""<<escape(src.filename().string())<<"\",";
    out<<"\"bytes\":"<<b.size()<<",\"imageBase\":\""<<hex(imagebase)<<"\",\n";
    out<<" \"caution\":\"RIP-relative xrefs are byte-pattern CANDIDATES, not proven function offsets; ASLR and game updates change live addresses\",\n";
    out<<" \"sections\":[";
    for(size_t i=0;i<list.size();i++){
        const auto& s=list[i];if(i)out<<',';
        out<<"{\"name\":\""<<escape(s.name)<<"\",\"rva\":\""<<hex(s.rva)<<"\",\"rawOffset\":\""
           <<hex(s.off)<<"\",\"rawBytes\":"<<s.raw<<",\"executable\":"
           <<(s.executable?"true":"false")<<"}";
    }
    out<<"],\n \"patterns\":[";
    std::size_t hits=0;
    for(size_t k=0;k<terms.size();k++){
        if(k)out<<',';
        out<<"\n  {\"term\":\""<<terms[k]<<"\",\"occurrences\":[";
        size_t emitted=0;
        const auto& term=terms[k];
        for(size_t start=0;start+term.size()<=b.size();){
            auto it=std::search(b.begin()+start,b.end(),term.begin(),term.end());
            if(it==b.end())break;
            auto off=(size_t)(it-b.begin());
            start=off+term.size();
            if(emitted>=48)break;
            const uint32_t rva=raw2rva((uint32_t)off);
            auto refs=rip_xrefs.equal_range(rva);
            if(emitted)out<<',';
            out<<"{\"offset\":\""<<hex(off)<<"\",\"rva\":\""<<hex(rva)
               <<"\",\"candidateRipReferences\":[";
            unsigned shown=0;
            for(auto p=refs.first;p!=refs.second&&shown<12;++p,++shown){
                if(shown)out<<',';
                out<<"\""<<hex(p->second)<<"\"";
            }
            out<<"]}";
            ++emitted;++hits;
        }
        out<<"],\"reportedCount\":"<<emitted<<"}";
    }
    out<<"\n ],\n \"ripPatternCandidateCount\":"<<rip_xrefs.size()<<"}\n";
    std::cout<<"PASS STATIC_PE_RECON sections="<<list.size()
             <<" patternOccurrences="<<hits<<" candidateRipXrefs="<<rip_xrefs.size()
             <<" inputBytes="<<b.size()
             <<" output="<<dest.string()
             <<" gameModified=false processAccessed=false\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"PE RECON ERROR "<<e.what()<<"\n";return 1;}

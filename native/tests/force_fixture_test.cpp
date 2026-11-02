#include "../src/force_worker_fixture.hpp"
#include <cstring>
#include <filesystem>
#include <iostream>

using namespace tm2020::research;
int main(int argc,char**argv) try {
    require(argc==2,"Usage: force_fixture_test temporary.bin");
    const std::filesystem::path file(argv[1]);
    struct Cleanup {std::filesystem::path path;~Cleanup(){std::error_code ec;std::filesystem::remove(path,ec);}} cleanup{file};
    const std::string sha(64,'0');
    std::vector<unsigned char> valid(12496);
    std::memcpy(valid.data(),"TMFWFX2",7);
    auto put32=[&](std::size_t at,std::uint32_t v){std::memcpy(valid.data()+at,&v,4);};
    auto put64=[&](std::size_t at,std::uint64_t v){std::memcpy(valid.data()+at,&v,8);};
    put32(8,2);put64(44,0x7ff600000000ull);put32(52,0x1000000);
    put32(56,1);put32(60,1);put32(64,88);put32(76,0x3c23d70b);put32(80,0x1f80);
    put32(196,0x851000);put64(200,0x700000000ull);valid[208]=1;
    auto write=[&](const auto& bytes){std::ofstream out(file,std::ios::binary);out.write(reinterpret_cast<const char*>(bytes.data()),std::streamsize(bytes.size()));require(bool(out),"Cannot create owned parser fixture");};
    write(valid);auto parsed=read_force_fixture(file.string().c_str(),sha);
    require(parsed.codePages.size()==1 && parsed.dataPages.size()==1,"Valid parser fixture failed");
    unsigned rejected{};
    auto reject=[&](const auto& bytes){write(bytes);bool failed=false;try{(void)read_force_fixture(file.string().c_str(),sha);}catch(const std::runtime_error&){failed=true;}require(failed,"Malformed fixture accepted");++rejected;};
    for(auto size:std::array<std::size_t,6>{0,8,43,196,207,12495})reject(std::vector<unsigned char>(valid.begin(),valid.begin()+size));
    for(auto at:std::array<std::size_t,7>{0,8,12,44,76,80,196}){auto b=valid;b[at]^=1;reject(b);}
    {auto b=valid;b[209]=2;reject(b);}
    {auto b=valid;b[4305]=1;reject(b);}
    {auto b=valid;b[8401]=1;reject(b);}
    {auto b=valid;const std::uint64_t address=0x300000000;std::memcpy(b.data()+200,&address,8);reject(b);}
    {auto b=valid;const std::uint64_t address=0xfffffffffffff000ull;std::memcpy(b.data()+200,&address,8);reject(b);}
    {auto b=valid;b.push_back(0);reject(b);}
    std::cout<<"PASS SPARSE FORCE FIXTURE valid=1 malformed_rejected="<<rejected<<'\n';
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}

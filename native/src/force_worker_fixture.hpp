#pragma once
// Trusted private research fixtures. No game code or unaccessed heap bytes.
#include <array>
#include <cstdint>
#include <fstream>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace tm2020::research {
inline void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
using Page = std::array<unsigned char, 4096>;
struct DataPage { std::uint64_t address{}; Page mask{}, initial{}, expected{}; };
struct ForceFixture {
    std::uint64_t base{}, timestamp{}, r9{}, forceAddress{}, vehicleAddress{};
    std::uint32_t imageSize{}, intervalBits{}, mxcsr{};
    std::array<unsigned char, 88> context{};
    std::vector<std::uint32_t> codePages;
    std::vector<DataPage> dataPages;
};
inline ForceFixture read_force_fixture(const char* path, const std::string& expectedSha) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    require(bool(file), "Cannot read force fixture");
    const auto size = file.tellg();
    require(size > 0 && size <= 8*1024*1024, "Force fixture size bound");
    file.seekg(0);
    auto read = [&](void* out, std::size_t count) {
        file.read(static_cast<char*>(out), std::streamsize(count));
        require(bool(file), "Truncated force fixture");
    };
    auto u32 = [&] { std::uint32_t v{}; read(&v, 4); return v; };
    auto u64 = [&] { std::uint64_t v{}; read(&v, 8); return v; };
    std::array<char, 8> magic{}; read(magic.data(), 8);
    require(magic == std::array<char,8>{'T','M','F','W','F','X','2',0} && u32()==2,
            "Unknown force fixture format");
    std::array<unsigned char,32> digest{}; read(digest.data(), digest.size());
    std::string hex;
    for (auto b : digest) { hex += "0123456789abcdef"[b>>4]; hex += "0123456789abcdef"[b&15]; }
    require(hex == expectedSha, "Force fixture build differs from original executable");
    ForceFixture f;
    f.base=u64(); f.imageSize=u32(); const auto nc=u32(), nd=u32(), ns=u32();
    require(f.base>=0x100000000ull && f.base<0x7fff00000000ull && f.base%65536==0 &&
            f.imageSize>0 && f.imageSize<128*1024*1024 && nc>0 && nc<=512 && nd>0 && nd<=512 && ns==88,
            "Invalid force fixture extents");
    f.timestamp=u64(); f.intervalBits=u32(); f.mxcsr=u32(); f.r9=u64();
    f.forceAddress=u64(); f.vehicleAddress=u64(); read(f.context.data(), 88);
    require(f.mxcsr==0x1f80 && f.intervalBits==0x3c23d70b, "Unsupported worker interval/MXCSR");
    f.codePages.resize(nc); read(f.codePages.data(), nc*4);
    std::set<std::uint64_t> seen;
    bool entry=false;
    for (auto rva : f.codePages) {
        require(rva%4096==0 && std::uint64_t(rva)+4096<=f.imageSize && seen.insert(f.base+rva).second,
                "Invalid/duplicate force code page");
        entry |= rva==(0x851f00&~4095);
    }
    require(entry, "Worker entry page missing");
    f.dataPages.resize(nd);
    for (auto& p : f.dataPages) {
        p.address=u64(); read(p.mask.data(),4096); read(p.initial.data(),4096); read(p.expected.data(),4096);
        require(p.address%4096==0 && seen.insert(p.address).second, "Duplicate/misaligned force data page");
        require((p.address>=f.base && p.address<=f.base+f.imageSize-4096) ||
                (p.address>=0x100000000ull && p.address<=0x40000000000ull-4096),
                "Force data page exceeds owned address domain");
        for (const auto [start, extent] : std::array<std::pair<std::uint64_t,std::uint64_t>,4>{{
                {0x200000000ull,0x10000}, {0x300000000ull,0x4000},
                {0x400000000ull,0x20000}, {0x500000000ull,0x1000}}})
            require(!(start<p.address+4096 && p.address<start+extent), "Fixture collides with offline synthetic memory");
        for (unsigned i=0;i<4096;++i)
            require(p.mask[i]<=1 && (p.mask[i] || (p.initial[i]==0 && p.expected[i]==0)),
                    "Unaccessed source bytes retained or invalid mask");
    }
    require(file.peek()==std::char_traits<char>::eof(), "Trailing force fixture data");
    return f;
}
}

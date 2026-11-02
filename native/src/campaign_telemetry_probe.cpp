// Read-only official shared telemetry. This process never opens game memory.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <array>
#include <cstring>
#include <iostream>
#include <string>

struct Sample {bool valid{};unsigned state{};std::string uid;};
Sample decode(const std::array<unsigned char,560>& b){
    unsigned version{},size{},state{};
    std::memcpy(&version,b.data()+32,4);std::memcpy(&size,b.data()+36,4);std::memcpy(&state,b.data()+44,4);
    if(std::memcmp(b.data(),"ManiaPlanet_Telemetry",20)||(version!=2&&version!=3)||size<560)return {};
    std::size_t n{};while(n<64&&b[112+n])++n;
    if(n==64)return {};
    std::string uid(reinterpret_cast<const char*>(b.data()+112),n);
    for(unsigned char c:uid)if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'))return {};
    return {true,state,uid};
}
int main(int argc,char** argv){
    if(argc==2&&std::string(argv[1])=="--selftest"){
        std::array<unsigned char,560> b{};std::memcpy(b.data(),"ManiaPlanet_Telemetry",20);
        unsigned version=3,size=560,state=2;
        std::memcpy(b.data()+32,&version,4);std::memcpy(b.data()+36,&size,4);std::memcpy(b.data()+44,&state,4);
        std::memcpy(b.data()+112,"owned_map-02",12);
        auto s=decode(b);if(!s.valid||s.uid!="owned_map-02"||s.state!=2)return 1;
        b[112]='"';if(decode(b).valid)return 2;b[112]='o';
        b[32]=99;if(decode(b).valid)return 3;
        std::cout<<"PASS read-only telemetry header, UID/state, malformed version/UID rejection\n";return 0;
    }
    if(argc!=3){std::cerr<<"probe STOP_FILE MAX_SECONDS\n";return 1;}
    const auto seconds=std::stoul(argv[2]);if(seconds<1||seconds>86400)return 1;
    const auto started=GetTickCount64();
    while(GetTickCount64()-started<seconds*1000ull&&GetFileAttributesA(argv[1])==INVALID_FILE_ATTRIBUTES){
        Sample s;const auto mapping=OpenFileMappingW(FILE_MAP_READ,FALSE,L"ManiaPlanet_Telemetry");
        if(mapping){const auto p=static_cast<const unsigned char*>(MapViewOfFile(mapping,FILE_MAP_READ,0,0,4096));
            if(p){std::array<unsigned char,560>a{},b{};std::memcpy(a.data(),p,a.size());std::memcpy(b.data(),p,b.size());
                if(std::memcmp(a.data()+32,b.data()+32,16)==0&&std::memcmp(a.data()+112,b.data()+112,64)==0)s=decode(b);
                UnmapViewOfFile(p);
            }CloseHandle(mapping);
        }
        std::cout<<"{\"valid\":"<<(s.valid?"true":"false")<<",\"state\":"<<s.state<<",\"mapUid\":\""<<s.uid<<"\"}"<<std::endl;
        Sleep(500);
    }
    return 0;
}

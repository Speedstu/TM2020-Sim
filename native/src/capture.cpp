// Loopback-only telemetry collector for Trackmania Openplanet plugin.
// Source+output on H:. No access to game memory, process handles or DRM.
// Openplanet script is separately opt-in and NOT installed automatically.
// Windows TCP listener, newline-delimited JSON, limited records/bytes.
// Deliberately stores the raw physical readings unmodified for later validation.
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#pragma comment(lib, "ws2_32.lib")
namespace fs = std::filesystem;

static bool contains_schema(const std::string& line) {
    return line.find("\"schema\":\"tm2020_live_telemetry_v1\"")!=std::string::npos;
}
static int run(std::uint16_t port,const fs::path& output,std::size_t max_lines) {
    if(max_lines<1||max_lines>10'000'000)throw std::invalid_argument("Invalid max lines");
    if(output.empty())throw std::invalid_argument("Missing destination path");
    fs::create_directories(output.parent_path());
    WSADATA wsa{};
    if(WSAStartup(MAKEWORD(2,2),&wsa)!=0)throw std::runtime_error("WSAStartup failed");
    struct Cleanup{~Cleanup(){WSACleanup();}} cleanup;
    SOCKET server=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
    if(server==INVALID_SOCKET)throw std::runtime_error("socket failed");
    struct SClose{SOCKET s;~SClose(){if(s!=INVALID_SOCKET)closesocket(s);}} listener{server};
    sockaddr_in addr{};
    addr.sin_family=AF_INET;
    addr.sin_port=htons(port);
    addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK); // NEVER bind to 0.0.0.0
    if(bind(server,(sockaddr*)&addr,sizeof(addr))==SOCKET_ERROR)
        throw std::runtime_error("bind failed; port in use?");
    if(listen(server,2)==SOCKET_ERROR)throw std::runtime_error("listen failed");
    std::ofstream file(output,std::ios::binary|std::ios::app);
    if(!file)throw std::runtime_error("Cannot open telemetry file");
    std::cout<<"READY 127.0.0.1:"<<port<<" output="<<output.string()<<std::endl;
    std::size_t lines=0,discarded=0,connections=0;
    constexpr std::size_t max_line=8192;
    constexpr std::size_t max_buffer=16384;
    while(lines<max_lines){
        SOCKET client=accept(server,nullptr,nullptr);
        if(client==INVALID_SOCKET)break;
        ++connections;
        SClose c{client};
        DWORD timeout=10000;
        setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,reinterpret_cast<const char*>(&timeout),sizeof(timeout));
        std::string buffer;
        bool overflow=false;
        char chunk[4096];
        while(lines<max_lines) {
            auto n=recv(client,chunk,sizeof(chunk),0);
            if(n<=0)break;
            for(int i=0;i<n;i++){
                const char ch=chunk[i];
                if(ch=='\n'){
                    if(!overflow&&!buffer.empty()&&buffer.size()<=max_line&&contains_schema(buffer)){
                        file.write(buffer.data(),static_cast<std::streamsize>(buffer.size()));
                        file.put('\n');++lines;
                        if(lines%100==0)file.flush();
                    } else ++discarded;
                    buffer.clear();overflow=false;
                    if(lines>=max_lines)break;
                } else if(ch!='\r'&&!overflow) {
                    if(buffer.size()>=max_line){buffer.clear();overflow=true;}
                    else buffer.push_back(ch);
                }
            }
            if(buffer.size()>max_buffer)throw std::runtime_error("Buffer size violation");
        }
    }
    file.flush();
    std::cout<<"CAPTURED frames="<<lines<<" discarded="<<discarded
             <<" connections="<<connections<<std::endl;
    return lines>0?0:3;
}
int main(int argc,char** argv){
    try {
        if(argc<3||argc>4) {
            std::cerr<<"Usage: tm2020_capture <H:\\path\\telemetry.ndjson> <port> [max_frames]\n";
            return 2;
        }
        int p=std::stoi(argv[2]);
        if(p<1024||p>65535)throw std::invalid_argument("Port out of allowed range");
        std::size_t n=argc>=4?static_cast<std::size_t>(std::stoull(argv[3])):100000;
        return run(static_cast<std::uint16_t>(p),argv[1],n);
    }catch(const std::exception& e) {
        std::cerr<<"capture error: "<<e.what()<<"\n";return 1;
    }
}

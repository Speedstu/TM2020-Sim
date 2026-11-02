#include "tm2020/read_only_live.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <array>
#include <filesystem>
#include <fstream>
#include <iostream>
struct Context{std::filesystem::path path;std::string result;};
DWORD WINAPI hash_worker(void* raw){
    auto& context=*static_cast<Context*>(raw);
    try{context.result=tm2020::live::file_sha256(context.path);return 0;}catch(...){return 1;}
}
int main(int argc,char** argv){
    if(argc!=2)return 1;
    Context context{argv[1],{}};
    {std::ofstream out(context.path,std::ios::binary);std::array<char,4096> bytes;bytes.fill('a');
     for(int i=0;i<512;i++)out.write(bytes.data(),bytes.size());out.write(bytes.data(),17);if(!out)return 2;}
    const HANDLE thread=CreateThread(nullptr,256*1024,hash_worker,&context,STACK_SIZE_PARAM_IS_A_RESERVATION,nullptr);
    if(!thread)return 3;
    const auto wait=WaitForSingleObject(thread,10000);DWORD code{};
    if(wait!=WAIT_OBJECT_0){CloseHandle(thread);return 4;}
    GetExitCodeThread(thread,&code);CloseHandle(thread);std::filesystem::remove(context.path);
    if(code||context.result!="c2273a45bd6d19d2714b8279b1fd1123bb746e7f7f6331085fb6ecaa30164546")return 5;
    std::cout<<"PASS SHA_WORKER stack_reserve_kib=256 input_bytes=2097169 digest_verified=true\n";
}

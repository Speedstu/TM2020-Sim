// Explicit SDK worker entry. No automatic worker or hook from DllMain.
#include "drive_session.hpp"
#include "tm2020/read_only_live.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include "tm2020/runtime.h"
#include <array>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

extern "C" __declspec(dllexport) DWORD WINAPI tm2020_runtime_probe(void* p) noexcept {
    if(p)return 0;
    try{
        std::vector<wchar_t> image(32768);
        if(!GetModuleFileNameW(nullptr,image.data(),static_cast<DWORD>(image.size())))return 0;
        return tm2020::live::file_sha256(std::filesystem::path(image.data())).size()==64?1:0;
    }catch(...){return 0;}
}

extern "C" __declspec(dllexport) DWORD WINAPI tm2020_bot_run(void* parameter) noexcept {
    if(!parameter)return 3;
    try {
        // Loader owns this bounded, NUL-terminated path until this call returns.
        const auto* raw=static_cast<const wchar_t*>(parameter);
        std::size_t size=0;while(size<32768&&raw[size])size++;
        if(size==0||size==32768)return 3;
        const std::filesystem::path config(std::wstring(raw,size));
        if(!config.is_absolute())return 3;
        std::array<wchar_t,32768> image{};
        if(!GetModuleFileNameW(nullptr,image.data(),static_cast<DWORD>(image.size()))||
            _wcsicmp(std::filesystem::path(image.data()).filename().c_str(),L"Trackmania.exe"))return 4;
        const auto name=L"Local\\TM2020NativeBot-"+std::to_wstring(GetCurrentProcessId());
        const HANDLE mutex=CreateMutexW(nullptr,FALSE,name.c_str());
        if(!mutex)return 5;
        struct Mutex{HANDLE h;bool held=false;~Mutex(){if(held)ReleaseMutex(h);CloseHandle(h);}} lock{mutex};
        const auto wait=WaitForSingleObject(mutex,0);
        if(wait!=WAIT_OBJECT_0&&wait!=WAIT_ABANDONED)return 2;
        lock.held=true;
        std::ifstream in(config);std::string line;
        if(!std::getline(in,line)||line!="TM2020_LOCAL_BOT_ARGUMENTS_V1")return 3;
        std::vector<std::string> arguments{"tm2020_injected_worker"};
        while(std::getline(in,line)){
            if(line.empty()||line.size()>32768||arguments.size()>=64)return 3;
            arguments.push_back(line);
        }
        if(arguments.size()<10||arguments[1]!="--confirm-local-solo")return 3;
        tm2020::live::ReadOnlyObserver identity(arguments[2]);
        if(identity.process_id()!=GetCurrentProcessId())return 4;
        const auto status_path=config.wstring()+L".status";
        auto status=[&](const char* phase,int result){
            std::ofstream out{std::filesystem::path(status_path)};
            out<<"TM2020_INJECTED_WORKER_STATUS_V1\n"<<GetCurrentProcessId()<<'\n'<<phase<<'\n'<<result<<'\n';
        };
        status("RUNNING",-1);
        std::vector<char*> argv;for(auto& argument:arguments)argv.push_back(argument.data());
        const int result=tm2020::live::run_drive_cli(static_cast<int>(argv.size()),argv.data());
        status("RETURNED",result);
        return static_cast<DWORD>(result);
    }catch(...){return 6;}
}

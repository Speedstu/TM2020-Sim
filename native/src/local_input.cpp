#include "tm2020/local_input.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <string>
#include <thread>
#include <chrono>
namespace tm2020::live {
namespace {
struct XusbReport {WORD buttons;BYTE left_trigger,right_trigger;SHORT left_x,left_y,right_x,right_y;};
static_assert(sizeof(XusbReport)==12);
using Allocate=void* (__cdecl*)();
using Free=void (__cdecl*)(void*);
using Connect=unsigned (__cdecl*)(void*);
using Pair=unsigned (__cdecl*)(void*,void*);
using Update=unsigned (__cdecl*)(void*,void*,XusbReport);
constexpr unsigned success=0x20000000;
void key(WORD scan,bool down,bool extended=true){
    INPUT i{};i.type=INPUT_KEYBOARD;i.ki.wScan=scan;
    i.ki.dwFlags=KEYEVENTF_SCANCODE|(extended?KEYEVENTF_EXTENDEDKEY:0)|(down?0:KEYEVENTF_KEYUP);
    if(SendInput(1,&i,sizeof(i))!=1)throw std::runtime_error("SendInput did not accept keyboard report");
}
}
struct LocalInput::Impl {
    std::uint32_t pid{};InputBackend backend{};HANDLE game{};
    HMODULE library{};void* client{};void* pad{};bool added{};
    Allocate alloc{},target_alloc{};Free free_client{},target_free{},disconnect{};
    Connect connect{};Pair add{},remove{};Update update{};
    std::array<bool,4> held{};
    double steering_accumulator{};
    ~Impl(){
        neutral();
        if(added)remove(client,pad);
        if(pad&&target_free)target_free(pad);
        if(client&&disconnect)disconnect(client);
        if(client&&free_client)free_client(client);
        if(library)FreeLibrary(library);
        if(game)CloseHandle(game);
    }
    bool foreground()const{
        DWORD current{};GetWindowThreadProcessId(GetForegroundWindow(),&current);
        return current==pid && WaitForSingleObject(game,0)==WAIT_TIMEOUT;
    }
    void neutral()noexcept{
        if(backend==InputBackend::ViGEmXbox360){
            if(added&&update)update(client,pad,{});
        }else{
            constexpr WORD scans[]={0x48,0x50,0x4b,0x4d};
            for(std::size_t i=0;i<held.size();i++)if(held[i]){
                try{key(scans[i],false);}catch(...){}held[i]=false;
            }
        }
    }
};
LocalInput::LocalInput(std::uint32_t pid,InputBackend backend,const std::filesystem::path& path)
    :impl_(std::make_unique<Impl>()){
    impl_->pid=pid;impl_->backend=backend;
    impl_->game=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,pid);
    if(!impl_->game)throw std::runtime_error("Cannot bind input lifetime to game process");
    std::array<wchar_t,32768> image{};DWORD size=static_cast<DWORD>(image.size());
    if(!QueryFullProcessImageNameW(impl_->game,0,image.data(),&size)||
       _wcsicmp(std::filesystem::path(std::wstring(image.data(),size)).filename().c_str(),L"Trackmania.exe"))
        throw std::invalid_argument("Input target is not Trackmania.exe");
    if(!impl_->foreground())throw std::runtime_error("Trackmania is not foreground");
    if(backend==InputBackend::ViGEmXbox360){
        if(!path.is_absolute())throw std::invalid_argument("ViGEmClient DLL requires an absolute path");
        impl_->library=LoadLibraryExW(path.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
        if(!impl_->library)throw std::runtime_error("Cannot load supplied ViGEmClient DLL");
        auto resolve=[&](const char* symbol){
            const auto p=GetProcAddress(impl_->library,symbol);
            if(!p)throw std::runtime_error(std::string("Missing ViGEm export: ")+symbol);return p;
        };
        impl_->alloc=reinterpret_cast<Allocate>(resolve("vigem_alloc"));
        impl_->free_client=reinterpret_cast<Free>(resolve("vigem_free"));
        impl_->connect=reinterpret_cast<Connect>(resolve("vigem_connect"));
        impl_->disconnect=reinterpret_cast<Free>(resolve("vigem_disconnect"));
        impl_->target_alloc=reinterpret_cast<Allocate>(resolve("vigem_target_x360_alloc"));
        impl_->target_free=reinterpret_cast<Free>(resolve("vigem_target_free"));
        impl_->add=reinterpret_cast<Pair>(resolve("vigem_target_add"));
        impl_->remove=reinterpret_cast<Pair>(resolve("vigem_target_remove"));
        impl_->update=reinterpret_cast<Update>(resolve("vigem_target_x360_update"));
        impl_->client=impl_->alloc();
        if(!impl_->client||impl_->connect(impl_->client)!=success)throw std::runtime_error("ViGEmBus connection failed");
        impl_->pad=impl_->target_alloc();
        if(!impl_->pad)throw std::runtime_error("ViGEm target allocation failed");
        const auto result=impl_->add(impl_->client,impl_->pad);
        if(result!=success)throw std::runtime_error("ViGEm target creation failed, status="+std::to_string(result));
        impl_->added=true;
    }
}
LocalInput::~LocalInput()=default;
void LocalInput::neutral()noexcept{impl_->neutral();}
void LocalInput::restart(){
    neutral();
    if(!impl_->foreground())throw std::runtime_error("Cannot restart: Trackmania is not foreground");
    key(0x53,true);
    std::this_thread::sleep_for(std::chrono::milliseconds(120));
    key(0x53,false);
}
void LocalInput::start_race(){
    neutral();
    if(!impl_->foreground())throw std::runtime_error("Cannot start: Trackmania is not foreground");
    key(0x1c,true,false);std::this_thread::sleep_for(std::chrono::milliseconds(150));key(0x1c,false,false);
    if(impl_->backend==InputBackend::ViGEmXbox360){
        // The Solo presentation accepts the pad's A button; a trigger alone
        // need not dismiss it. Keep the button release explicit on every path.
        XusbReport report{};report.buttons=0x1000;
        if(impl_->update(impl_->client,impl_->pad,report)!=success)throw std::runtime_error("ViGEm start button failed");
        std::this_thread::sleep_for(std::chrono::milliseconds(180));neutral();
    }
}
void LocalInput::apply(Controls c){
    if(!std::isfinite(c.steer)||!std::isfinite(c.gas)||!std::isfinite(c.brake)||
       std::abs(c.steer)>1||c.gas<0||c.gas>1||c.brake<0||c.brake>1){
        neutral();throw std::invalid_argument("Input controls outside normalized range");
    }
    if(!impl_->foreground()||(GetAsyncKeyState(VK_ESCAPE)&0x8000)){
        neutral();throw std::runtime_error("Input stopped: game lost focus, exited, or Escape held");
    }
    if(impl_->backend==InputBackend::ViGEmXbox360){
        XusbReport r{};r.left_x=static_cast<SHORT>(std::lround(c.steer*32767));
        r.right_trigger=static_cast<BYTE>(std::lround(c.gas*255));
        r.left_trigger=static_cast<BYTE>(std::lround(c.brake*255));
        if(impl_->update(impl_->client,impl_->pad,r)!=success){neutral();throw std::runtime_error("ViGEm update failed");}
    }else{
        // Keyboard is deliberately discrete. Analog training uses the gamepad.
        impl_->steering_accumulator+=std::abs(c.steer);
        const bool pulse=impl_->steering_accumulator>=1.;
        if(pulse)impl_->steering_accumulator-=1.;
        const std::array<bool,4> next{c.gas>.5,c.brake>.5,pulse&&c.steer<0,pulse&&c.steer>0};
        constexpr WORD scans[]={0x48,0x50,0x4b,0x4d};
        try{for(std::size_t i=0;i<next.size();i++)if(next[i]!=impl_->held[i]){
            key(scans[i],next[i]);impl_->held[i]=next[i];
        }}catch(...){neutral();throw;}
    }
}
}

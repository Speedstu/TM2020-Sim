#pragma once
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <array>
#include <atomic>
#include <cstring>
#include <stdexcept>
#include <string>
#include <span>

namespace tm2020::internal {
inline constexpr std::array<unsigned char,13> consumer_prologue{
    0x48,0x8b,0xc4,0x53,0x41,0x55,0x48,0x81,0xec,0xa8,0,0,0};
// input_overrides(ForceCtx*), before Sport's cached gas_on/brake_on.
// Whole instructions only; no relative branch or RIP-relative operand.
inline constexpr std::array<unsigned char,18> early_consumer_prologue{
    0x48,0x83,0xec,0x28,0x4c,0x8b,0x49,0x08,0x4c,0x8b,0xd9,
    0x49,0x8d,0x89,0x80,0x12,0,0};
inline constexpr std::array<unsigned char,17> input_decoder_prologue{
    0x4c,0x89,0x4c,0x24,0x20,0x48,0x89,0x4c,0x24,0x08,
    0x55,0x53,0x57,0x41,0x55,0x41,0x56};
class PausedThreads {
    std::array<HANDLE,512> handles_{};std::size_t count_{},paused_{};
public:
    const char* failure="none";DWORD error{},thread{};std::uintptr_t ip{};
    PausedThreads(){
        auto snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);
        if(snapshot==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot enumerate owned process threads");
        THREADENTRY32 entry{};entry.dwSize=sizeof(entry);bool ok=true;
        if(Thread32First(snapshot,&entry))do{
            if(entry.th32OwnerProcessID!=GetCurrentProcessId()||entry.th32ThreadID==GetCurrentThreadId())continue;
            if(count_==handles_.size()){ok=false;break;}
            auto h=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT|THREAD_QUERY_INFORMATION,FALSE,entry.th32ThreadID);
            if(!h){ok=false;break;}handles_[count_++]=h;
        }while(Thread32Next(snapshot,&entry));
        CloseHandle(snapshot);
        if(!ok){resume();throw std::runtime_error("Cannot inspect every owned process thread; hook refused");}
    }
    bool pause()noexcept{
        for(;paused_<count_;++paused_)if(SuspendThread(handles_[paused_])==DWORD(-1)){failure="SuspendThread";error=GetLastError();thread=GetThreadId(handles_[paused_]);return false;}
        return true;
    }
    bool outside(const void* start,std::size_t bytes)noexcept{
        const auto lo=reinterpret_cast<std::uintptr_t>(start);
        for(std::size_t i=0;i<paused_;++i){CONTEXT context{};context.ContextFlags=CONTEXT_CONTROL;
            if(!GetThreadContext(handles_[i],&context)){failure="GetThreadContext";error=GetLastError();thread=GetThreadId(handles_[i]);return false;}
            if(context.Rip>=lo&&context.Rip<lo+bytes){failure="instruction_pointer_in_patch";thread=GetThreadId(handles_[i]);ip=context.Rip;return false;}
        }return true;
    }
    void resume()noexcept{
        for(std::size_t i=0;i<paused_;++i)ResumeThread(handles_[i]);paused_=0;
        for(std::size_t i=0;i<count_;++i)CloseHandle(handles_[i]);count_=0;
    }
    ~PausedThreads(){resume();}
};
// Exact pinned whole-instruction prologues, no RIP-relative instructions. No signature scans,
// debugger tricks, protection bypass or forced thread termination.
class ConsumerHook {
    unsigned char* entry_{};unsigned char* trampoline_{};bool installed_{};
    DWORD write_protection_=PAGE_EXECUTE_READWRITE;
    bool debug_write_{};std::array<unsigned char,32> installed_bytes_{},saved_bytes_{};std::size_t patch_size_{13};
    HANDLE proc_memory_=INVALID_HANDLE_VALUE;std::uint64_t proc_nonce_{};
    const char* failure_="none";DWORD error_{},thread_{};std::uintptr_t ip_{};
public:
    void use_debug_writer(bool enabled)noexcept{debug_write_=enabled;}
    void use_proc_debug_writer(const std::wstring& path){
        if(installed_)throw std::runtime_error("Cannot change an active hook writer");
        const std::wstring prefix=L"Z:\\proc\\",suffix=L"\\mem";
        if(!path.starts_with(prefix)||!path.ends_with(suffix)||path.size()<=prefix.size()+suffix.size())throw std::runtime_error("Expected explicit Wine namespace process memory path");
        for(auto c:path.substr(prefix.size(),path.size()-prefix.size()-suffix.size()))if(c<L'0'||c>L'9')throw std::runtime_error("Invalid process memory PID");
        if(proc_memory_!=INVALID_HANDLE_VALUE)CloseHandle(proc_memory_);
        proc_memory_=CreateFileW(path.c_str(),GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(proc_memory_==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot open explicitly authorized process memory file");
        proc_nonce_=0xb4a3d2c196f5807eull^reinterpret_cast<std::uintptr_t>(this)^GetTickCount64()^(std::uint64_t(GetCurrentProcessId())<<32);
        LARGE_INTEGER at{};at.QuadPart=reinterpret_cast<std::uintptr_t>(&proc_nonce_);std::uint64_t copy{};DWORD n{};
        if(!SetFilePointerEx(proc_memory_,at,nullptr,FILE_BEGIN)||!ReadFile(proc_memory_,&copy,sizeof(copy),&n,nullptr)||n!=sizeof(copy)||copy!=proc_nonce_){CloseHandle(proc_memory_);proc_memory_=INVALID_HANDLE_VALUE;throw std::runtime_error("Process memory nonce mismatch; refuses another process");}
    }
    bool proc_write(const unsigned char* bytes)noexcept{
        LARGE_INTEGER at{};at.QuadPart=reinterpret_cast<std::uintptr_t>(entry_);DWORD n{};
        return SetFilePointerEx(proc_memory_,at,nullptr,FILE_BEGIN)&&WriteFile(proc_memory_,bytes,patch_size_,&n,nullptr)&&n==patch_size_&&std::memcmp(entry_,bytes,patch_size_)==0;
    }
    std::string diagnostic()const{return std::string(failure_)+" win32="+std::to_string(error_)+" thread="+std::to_string(thread_)+" ip="+std::to_string(ip_);}
    void* original()const noexcept{return trampoline_;}
    bool installed()const noexcept{return installed_;}
    void prepare(void* entry,std::span<const unsigned char> expected=consumer_prologue){
        if(expected.size()<13||expected.size()>32)throw std::runtime_error("Invalid pinned hook length");
        // A callback may be scheduled immediately before its first inflight
        // increment. Keep its trampoline alive for the process lifetime, and
        // reuse it only for the same pinned consumer.
        if(entry_==entry&&trampoline_&&!installed_){
            if(expected.size()!=patch_size_||std::memcmp(entry,expected.data(),patch_size_)||std::memcmp(saved_bytes_.data(),expected.data(),patch_size_))
                throw std::runtime_error("Consumer entry changed after detach");
            return;
        }
        if(entry_||std::memcmp(entry,expected.data(),expected.size()))
            throw std::runtime_error("Unsupported consumer entry bytes");
        patch_size_=expected.size();std::memcpy(saved_bytes_.data(),expected.data(),patch_size_);
        entry_=static_cast<unsigned char*>(entry);
        MEMORY_BASIC_INFORMATION memory{};
        if(!VirtualQuery(entry_,&memory,sizeof(memory)))throw std::runtime_error("Cannot inspect consumer allocation");
        // Respect a mapped image's original copy-on-write access. Requesting
        // shared READWRITE on a WRITECOPY image can be rejected by Wine.
        // No fallback to native syscalls or alternate write mechanisms.
        if((memory.Type==MEM_IMAGE||memory.Type==MEM_MAPPED)&&
           (memory.AllocationProtect&0xff)==PAGE_EXECUTE_WRITECOPY)write_protection_=PAGE_EXECUTE_WRITECOPY;
        trampoline_=static_cast<unsigned char*>(VirtualAlloc(nullptr,64,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
        if(!trampoline_)throw std::runtime_error("Cannot allocate owned trampoline");
        std::memcpy(trampoline_,entry_,patch_size_);
        const unsigned char jump[]{0xff,0x25,0,0,0,0};std::memcpy(trampoline_+patch_size_,jump,6);
        auto next=entry_+patch_size_;std::memcpy(trampoline_+patch_size_+6,&next,8);DWORD old{};
        if(!VirtualProtect(trampoline_,64,PAGE_EXECUTE_READ,&old))throw std::runtime_error("Cannot seal owned trampoline");
        FlushInstructionCache(GetCurrentProcess(),trampoline_,64);
    }
    bool install(void* callback){
        if(!trampoline_||installed_)return false;
        std::array<unsigned char,32> jump{};jump.fill(0x90);
        if(patch_size_>=14){
            // Preserve every input register before the naked callback can
            // save it. A mov-r11/jmp-r11 patch would already destroy R11.
            jump[0]=0xff;jump[1]=0x25;std::memset(jump.data()+2,0,4);
            std::memcpy(jump.data()+6,&callback,8);
        }else{
            // Legacy 13-byte fixture only; both game entries use >=17 bytes.
            jump[0]=0x49;jump[1]=0xbb;std::memcpy(jump.data()+2,&callback,8);
            jump[10]=0x41;jump[11]=0xff;jump[12]=0xe3;
        }
        installed_bytes_=jump;
        PausedThreads threads;bool ok=threads.pause()&&threads.outside(entry_,patch_size_);
        if(!ok){failure_=threads.failure;error_=threads.error;thread_=threads.thread;ip_=threads.ip;}
        DWORD old{},ignored{};
        if(ok){ok=std::memcmp(entry_,saved_bytes_.data(),patch_size_)==0;if(!ok)failure_="entry_bytes_changed";}
        if(ok&&proc_memory_!=INVALID_HANDLE_VALUE){
            ok=proc_write(jump.data());if(!ok){failure_="proc_debug_install";error_=GetLastError();}
            if(ok){FlushInstructionCache(GetCurrentProcess(),entry_,patch_size_);installed_=true;}
        }else if(ok&&debug_write_){
            SIZE_T written{};ok=WriteProcessMemory(GetCurrentProcess(),entry_,jump.data(),patch_size_,&written)&&written==patch_size_;
            if(!ok){failure_="WriteProcessMemory_install";error_=GetLastError();}
            if(ok){FlushInstructionCache(GetCurrentProcess(),entry_,patch_size_);installed_=true;}
        }else if(ok){
            ok=VirtualProtect(entry_,patch_size_,write_protection_,&old)!=0;if(!ok){failure_="VirtualProtect_install";error_=GetLastError();}
            if(ok){std::memcpy(entry_,jump.data(),patch_size_);FlushInstructionCache(GetCurrentProcess(),entry_,patch_size_);
                installed_=true;ok=VirtualProtect(entry_,patch_size_,old,&ignored)!=0;if(!ok){failure_="VirtualProtect_restore";error_=GetLastError();}}
        }
        threads.resume();return ok;
    }
    bool remove(){
        if(!installed_)return true;
        PausedThreads threads;bool ok=threads.pause()&&threads.outside(entry_,patch_size_)&&threads.outside(trampoline_,64);
        if(ok)ok=std::memcmp(entry_,installed_bytes_.data(),patch_size_)==0;
        DWORD old{},ignored{};
        if(ok&&proc_memory_!=INVALID_HANDLE_VALUE){
            ok=proc_write(saved_bytes_.data());
            if(ok){FlushInstructionCache(GetCurrentProcess(),entry_,patch_size_);installed_=false;}
        }else if(ok&&debug_write_){
            SIZE_T written{};ok=WriteProcessMemory(GetCurrentProcess(),entry_,saved_bytes_.data(),patch_size_,&written)&&written==patch_size_;
            if(ok){FlushInstructionCache(GetCurrentProcess(),entry_,patch_size_);installed_=false;}
        }else if(ok){
            ok=VirtualProtect(entry_,patch_size_,write_protection_,&old)!=0;
            if(ok){std::memcpy(entry_,saved_bytes_.data(),patch_size_);FlushInstructionCache(GetCurrentProcess(),entry_,patch_size_);
                installed_=false;ok=VirtualProtect(entry_,patch_size_,old,&ignored)!=0;}
        }
        threads.resume();return ok;
    }
    // Intentionally retained with the pinned DLL. Counting callbacks cannot
    // prove that no thread is parked before the callback's first instruction.
};
}

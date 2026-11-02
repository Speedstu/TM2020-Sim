#include "tm2020/policy.h"
#include "tm2020/rl.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
void check(bool b,const char* message){if(!b)throw std::runtime_error(message);}
int main(int argc,char** argv)try{
    if(argc!=3)throw std::invalid_argument("policy_abi_test dll model");
    HMODULE dll=LoadLibraryW(std::filesystem::absolute(argv[1]).c_str());check(bool(dll),"Cannot load policy DLL");
    struct Dll{HMODULE p;~Dll(){FreeLibrary(p);}} guard{dll};
    auto sym=[&](const char* n){auto p=GetProcAddress(dll,n);check(bool(p),"Missing PPO ABI export");return p;};
    auto open=reinterpret_cast<decltype(&tm2020_policy_open)>(sym("tm2020_policy_open"));
    auto close=reinterpret_cast<decltype(&tm2020_policy_close)>(sym("tm2020_policy_close"));
    auto info=reinterpret_cast<decltype(&tm2020_policy_get_info)>(sym("tm2020_policy_get_info"));
    auto schema=reinterpret_cast<decltype(&tm2020_policy_schema)>(sym("tm2020_policy_schema"));
    auto predict=reinterpret_cast<decltype(&tm2020_policy_predict)>(sym("tm2020_policy_predict"));
    tm2020_policy_handle h{};check(open(argv[2],&h)==0&&h,"Model load failed");
    struct Policy{tm2020_policy_handle h;decltype(close) free;~Policy(){free(h);}} cleanup{h,close};
    tm2020_policy_info in{sizeof(in),1,0,0,0,0};check(info(h,&in)==0&&in.observation_count==1&&in.action_count==1,"PPO ABI shape mismatch");
    check(std::string(schema(h))=="synthetic_context_control_v1","PPO ABI observation schema mismatch");
    const auto direct=tm2020::rl::ActorCritic::load(argv[2]);double action{},value{},input=.45;
    check(predict(h,&input,1,&action,1,&value)==0,"PPO prediction failed");
    check(action==direct.deterministic(std::array{input}).action[0],"PPO ABI/direct inference diverged");
    input=std::numeric_limits<double>::quiet_NaN();
    check(predict(h,&input,1,&action,1,&value)!=0&&action==0&&value==0,"NaN was not neutralized");
    tm2020_policy_handle missing=reinterpret_cast<void*>(1);
    check(open("__missing.tmppo",&missing)!=0&&!missing,"Failed open left a stale handle");
    std::cout<<"PASS PPO_DLL_ABI parity=true schema=true nonfinite_denied=true independent_handles=true\n";
}catch(const std::exception& e){std::cerr<<"POLICY_ABI_ERROR "<<e.what()<<'\n';return 1;}

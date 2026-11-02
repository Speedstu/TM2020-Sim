// SPDX-License-Identifier: GPL-3.0-or-later
// Owned-process cross-platform perception/portable-policy parity harness.
#include "tm2020/rl.hpp"
#include <array>
#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif
int main(int argc,char** argv)try{
    const bool preview=argc==8&&std::string(argv[7])=="--preview";
    if(argc!=7&&!preview)throw std::runtime_error("Usage: probe perception-library map packs raw.f32 observations.f64 max-microseconds.txt [--preview]");
#ifdef _WIN32
    auto library=LoadLibraryA(argv[1]);
    auto symbol=[&](const char* name){return reinterpret_cast<void*>(GetProcAddress(library,name));};
#else
    auto library=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
    auto symbol=[&](const char* name){return dlsym(library,name);};
#endif
    if(!library)throw std::runtime_error("Cannot load owned perception library");
    auto open=reinterpret_cast<void*(*)(const char*,const char*,const char*,unsigned)>(symbol("tmfast_open"));
    auto observe=reinterpret_cast<int(*)(void*,const float*,unsigned,double*)>(symbol(preview?"tmgen_observe72":"tmgen_observe"));
    auto close=reinterpret_cast<void(*)(void*)>(symbol("tmfast_close"));
    auto error=reinterpret_cast<const char*(*)()>(symbol("tmfast_last_error"));
    if(!open||!observe||!close||!error)throw std::runtime_error("Missing perception export");
    auto env=open(argv[2],argv[3],"",4000);if(!env)throw std::runtime_error(error());
    std::ifstream input(argv[4],std::ios::binary);std::ofstream output(argv[5],std::ios::binary);
    if(!input||!output)throw std::runtime_error("Cannot open owned probe buffers");
    std::vector<float> raw(preview?24:21);std::vector<double> observation(preview?72:48);unsigned count{};double maximum{};
    while(input.read(reinterpret_cast<char*>(raw.data()),raw.size()*sizeof(float))){
        auto start=std::chrono::steady_clock::now();
        if(observe(env,raw.data(),count?0:1,observation.data()))throw std::runtime_error(error());
        maximum=std::max(maximum,std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count());
        output.write(reinterpret_cast<char*>(observation.data()),observation.size()*sizeof(double));++count;
    }
    if(!input.eof()||input.gcount()!=0||!count)throw std::runtime_error("Truncated/empty raw probe input");
    close(env);std::ofstream timing(argv[6]);timing<<maximum<<'\n';
    std::cout<<"PASS OWNED_PERCEPTION rows="<<count<<" max_us="<<maximum<<" game_accessed=false\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

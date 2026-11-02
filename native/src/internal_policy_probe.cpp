// SPDX-License-Identifier: GPL-3.0-or-later
#include "tm2020/rl.hpp"
#include "tm2020/hybrid_actions.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
int main(int argc,char** argv)try{
    if(argc!=4)throw std::runtime_error("Usage: policy-probe model.tmppo observations.f64 controls.f32");
    auto policy=tm2020::rl::ActorCritic::load(argv[1]);std::vector<double> x(policy.actor.inputs);
    std::ifstream input(argv[2],std::ios::binary);std::ofstream output(argv[3],std::ios::binary);
    if(!input||!output)throw std::runtime_error("Cannot open policy probe buffers");unsigned count{};
    while(input.read(reinterpret_cast<char*>(x.data()),x.size()*8)){
        auto values=policy.actor.forward(x);tm2020::internal::Controls controls{};
        if(!tm2020::internal::decode_actions(values,controls))throw std::runtime_error("Invalid raw policy head");
        output.write(reinterpret_cast<char*>(&controls),sizeof(controls));++count;
    }
    if(!input.eof()||input.gcount()!=0||!count)throw std::runtime_error("Truncated policy observations");
    std::cout<<"PASS PORTABLE_POLICY rows="<<count<<" outputs="<<policy.actor.outputs<<"\n";
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}

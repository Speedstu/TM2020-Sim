#include "tm2020/hybrid_actions.hpp"
#include <limits>
#include <stdexcept>
#include <iostream>
#include <vector>
using namespace tm2020::internal;
int main()try{
    Controls c{};
    for(auto bins:{17,33})for(int k=0;k<bins;++k){
        std::vector<double> head(bins+2,100.);head[0]=5.3;head[1]=-5.3;head[2+k]=101.;
        if(!decode_actions(head,c)||c.gas!=1||c.brake!=0||c.steer!=float(std::round((-1.+2.*k/(bins-1))*127.)/127.))throw std::runtime_error("Raw categorical argmax/quantization mismatch");
        head[2]=std::numeric_limits<double>::quiet_NaN();if(decode_actions(head,c))throw std::runtime_error("NaN head accepted");
    }
    for(double mean:{-1.,0.,1.}){
        const std::array<double,3> head{-1.,1.,mean};
        if(!decode_actions(head,c)||c.gas!=0||c.brake!=1||c.steer!=float(std::round(std::tanh(mean)*127.)/127.))throw std::runtime_error("Hybrid continuous decode mismatch");
    }
    std::cout<<"PASS raw hybrid heads: all 17/33 bins, saturation, pedals, continuous steering, NaN rejection\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

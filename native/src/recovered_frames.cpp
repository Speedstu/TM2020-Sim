#include "tm2020/recovered_frames.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
template<std::size_t N>void bounded(const std::array<float,N>& a){for(float x:a)if(!std::isfinite(x)||std::abs(x)>1e6f)throw std::invalid_argument("Model center frame exceeds finite domain");}
}
void shift_model_center_frame(std::span<RigidState> states,std::span<const std::array<float,3>> centers,bool subtract){
    if(states.size()!=centers.size()||states.size()>1000000)throw std::invalid_argument("Model center frame count mismatch");
    for(std::size_t j=0;j<states.size();j++){bounded(states[j].rotation);bounded(states[j].position);bounded(centers[j]);}
    auto next=std::vector<RigidState>(states.begin(),states.end());
    for(std::size_t j=0;j<next.size();j++){
        auto c=centers[j];if(subtract)for(float& x:c)x=-x;auto& s=next[j];const auto& r=s.rotation;
        s.position[0]=((c[0]*r[0]+c[1]*r[1])+c[2]*r[2])+s.position[0];
        s.position[1]=((r[4]*c[1]+r[3]*c[0])+r[5]*c[2])+s.position[1];
        s.position[2]=((c[0]*r[6]+c[1]*r[7])+c[2]*r[8])+s.position[2];bounded(s.position);
    }
    std::copy(next.begin(),next.end(),states.begin());
}
}

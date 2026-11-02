#pragma once
#include <algorithm>
#include <span>
#include <stdexcept>
#include <vector>
namespace tm2020::rl {
// Oldest to newest. Reset repeats the initial observation: no prior race leaks.
class ObservationHistory {
    std::size_t width_,frames_;
public:
    std::vector<double> values;
    ObservationHistory(std::size_t width=48,std::size_t frames=1):width_(width),frames_(frames),values(width*frames){
        if(!width||(frames!=1&&frames!=3&&frames!=5))throw std::invalid_argument("Unsupported observation history");
    }
    void reset(std::span<const double> x){
        if(x.size()!=width_)throw std::invalid_argument("History observation width differs");
        for(std::size_t i=0;i<frames_;++i)std::copy(x.begin(),x.end(),values.begin()+i*width_);
    }
    void push(std::span<const double> x){
        if(x.size()!=width_)throw std::invalid_argument("History observation width differs");
        std::move(values.begin()+width_,values.end(),values.begin());
        std::copy(x.begin(),x.end(),values.end()-width_);
    }
};
inline std::size_t observation_frames(std::size_t inputs,std::size_t width=48){
    if(width!=48&&width!=72)throw std::invalid_argument("Unsupported observation width");
    if(inputs==width)return 1;
    if(inputs==width*3)return 3;
    if(inputs==width*5)return 5;
    throw std::invalid_argument("Policy requires 48, 144 or 240 causal observations");
}
}

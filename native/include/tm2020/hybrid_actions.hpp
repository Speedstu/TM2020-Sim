#pragma once
#include "tm2020/internal_tick.hpp"
#include <algorithm>
#include <span>
namespace tm2020::internal {
// Raw head values: pedals are Bernoulli logits; categorical steering uses
// argmax BEFORE tanh (large logits must not collapse into saturated ties).
inline bool decode_actions(std::span<const double> values,Controls& out)noexcept{
    out={};for(auto x:values)if(!std::isfinite(x))return false;
    double steer{};
    if(values.size()==1){out.gas=1;steer=std::tanh(values[0]);}
    else if(values.size()==3){out.gas=float(values[0]>=0);out.brake=float(values[1]>=0);steer=std::tanh(values[2]);}
    else if(values.size()==19||values.size()==35){
        out.gas=float(values[0]>=0);out.brake=float(values[1]>=0);
        const auto bins=values.subspan(2);const auto k=std::max_element(bins.begin(),bins.end())-bins.begin();
        steer=-1.+2.*double(k)/double(bins.size()-1);
    }else return false;
    out.steer=float(std::round(steer*127.)/127.);return valid(out);
}
}

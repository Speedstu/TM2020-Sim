#include "tm2020/recovered_activation.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
bool enqueue_body_wake(bool callback_present,std::uint32_t slot,
    std::span<WakeIndexState> indices,std::span<const std::uint32_t> handles,
    std::vector<std::uint32_t>& pending){
    if(!callback_present)return false;
    if(slot>=indices.size())throw std::invalid_argument("Wake body slot exceeds index table");
    auto& state=indices[slot];
    if(state.active_index!=0xffff||state.queued==1)return false;
    if(slot>=handles.size()||pending.size()>=65535)throw std::invalid_argument("Wake queue/map domain");
    pending.push_back(handles[slot]);state.queued=1;return true;
}
bool activate_body_slot(WakeIndexState& state,std::uint32_t slot,
    std::span<std::uint32_t> active,std::uint32_t& count){
    if(state.active_index!=0xffff)return false;
    if(count>=active.size()||count>0xffff)throw std::invalid_argument("Active body list domain");
    const auto old=count++;active[old]=slot;state.active_index=std::uint16_t(old);return true;
}
bool model_fixed_for_flags(std::uint32_t word,std::uint8_t flags) noexcept{return word!=0&&(flags&8)==0;}
void prepare_body_activation(std::span<BodyActivationState> states,
    std::span<const BodyActivationInput> inputs,std::span<const std::uint32_t> ids){
    auto require=[](bool valid,const char* message){if(!valid)throw std::invalid_argument(message);};
    require(states.size()==inputs.size()&&states.size()<=1000000&&ids.size()<=1000000,"Invalid body activation extent");
    for(std::size_t n=0;n<inputs.size();n++){
        const auto& p=inputs[n];
        require(std::isfinite(p.model_mass)&&std::isfinite(p.item_mass_offset)&&std::abs(p.model_mass)<=1e6f&&std::abs(p.item_mass_offset)<=1e6f&&p.model_mass+p.item_mass_offset>=1e-6f,"Invalid activation mass coefficient");
        require(states[n].related_item_id==0xffffffff||states[n].related_item_id<ids.size(),"Activation related item ID exceeds map");
    }
    auto next=std::vector<BodyActivationState>(states.begin(),states.end());
    for(std::size_t n=0;n<next.size();n++){
        auto& s=next[n];const auto& p=inputs[n];const auto f=p.source_flags;
        const bool fixed=model_fixed_for_flags(p.model_word_50,f);
        std::uint8_t flags=std::uint8_t((s.flags&0xfeu)|std::uint32_t(fixed));
        s.related_state_index=s.related_item_id==0xffffffff?0xffffffff:ids[s.related_item_id];
        const bool disabled=(f&5)!=0||fixed;
        flags=std::uint8_t((flags&0xedu)|(disabled?0x12u:0u));
        const bool special=p.shape_present&&p.shape_tag_11==7;
        const bool no_force=((f&1)!=0&&!special)||fixed||(f&4)!=0||!p.shape_present||p.sleep_word_4==0xffff;
        flags=std::uint8_t((flags&0xf3u)|(no_force?4u:0u));
        float inverse=1.f/(p.model_mass+p.item_mass_offset);
        if((f&1)!=0&&!special)inverse=0;
        flags=std::uint8_t((flags&0xdfu)|((f&2u)<<4));
        if((f&2)!=0){flags=std::uint8_t(flags|0x1e);inverse=0;}
        s.flags=(s.flags&0xffffff00u)|flags;s.coefficients[3]=inverse;
    }
    std::copy(next.begin(),next.end(),states.begin());
}
}

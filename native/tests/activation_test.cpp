#include "tm2020/recovered_activation.hpp"
#include "tm2020/recovered_step.hpp"
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool valid,const char* message){if(!valid)throw std::runtime_error(message);}
int main()try{
    std::array<WakeIndexState,2> wake{};std::vector<std::uint32_t> queue;
    const std::array<std::uint32_t,2> reverse{17,99};wake[0].queued=2;wake[1].active_index=0;
    check(!enqueue_body_wake(false,500,wake,reverse,queue),"Disabled wake touched invalid slot");
    check(enqueue_body_wake(true,0,wake,reverse,queue)&&queue==std::vector<std::uint32_t>{17}&&wake[0].queued==1,"Wake reverse mapping or byte==1 gate differs");
    check(!enqueue_body_wake(true,0,wake,reverse,queue)&&!enqueue_body_wake(true,1,wake,reverse,queue)&&queue.size()==1,"Wake active/duplicate gate differs");
    std::array<std::uint32_t,3> active{7,8,9};std::uint32_t count=1;
    check(activate_body_slot(wake[0],42,active,count)&&count==2&&active[1]==42&&wake[0].active_index==1&&wake[0].queued==1,"Active list insertion differs");
    check(!activate_body_slot(wake[0],99,active,count)&&count==2,"Repeated activation mutated the active list");
    wake[1].active_index=0xffff;count=3;bool full_denied=false;
    try{activate_body_slot(wake[1],99,active,count);}catch(const std::invalid_argument&){full_denied=true;}
    check(full_denied&&count==3&&wake[1].active_index==0xffff,"Out-of-bounds activation was not transactional");
    std::array<BodyActivationState,2> states{};std::array<BodyActivationInput,2> inputs{};
    for(auto& s:states){s.flags=0xaabbccff;s.coefficients={1,2,3,4};}
    for(auto& p:inputs){p.model_mass=1500;p.shape_present=true;p.shape_tag_11=4;}
    states[0].related_item_id=1;const std::array<std::uint32_t,2> ids{10,20};
    prepare_body_activation(states,inputs,ids);
    check(states[0].flags==0xaabbccc0&&states[0].related_state_index==20&&states[0].coefficients==VelocityCoefficients{1,2,3,1.f/1500.f},"Awake activation changed unrelated bits or inertia lanes");
    inputs[0].source_flags=1;prepare_body_activation(states,inputs,ids);
    check(states[0].coefficients[3]==0&&(states[0].flags&0x16)==0x16,"Fixed source flags failed to disable body");
    inputs[0].shape_tag_11=7;prepare_body_activation(states,inputs,ids);
    check(states[0].coefficients[3]==1.f/1500.f&&(states[0].flags&4)==0,"Special shape-tag branch changed");
    inputs[0].source_flags=8;inputs[0].model_word_50=1;prepare_body_activation(states,inputs,ids);
    check((states[0].flags&3)==0,"Source override failed to clear model fixed state");
    inputs[1].model_mass=0;const auto before=states;bool denied=false;
    try{prepare_body_activation(states,inputs,ids);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(states.data(),before.data(),sizeof(states))==0,"Invalid late body partly committed activation batch");
    check(native_vehicle_interval_ms==10&&std::bit_cast<std::uint32_t>(native_vehicle_interval)==0x3c23d70b&&native_vehicle_interval!=.01f,"Exact engine time step changed");
    std::cout<<"PASS ACTIVATION flags=true special_shape=true ID_map=true transactional_batch=true exact_vehicle_interval=true\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}

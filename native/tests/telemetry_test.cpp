#include "tm2020/visual_state.hpp"
#include "tm2020/actuator.hpp"
#include <bit>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>
using namespace tm2020::live;
void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
ReflectedVisualState copy(std::uint32_t episode,std::uint32_t clock,float gas=0){
    ReflectedVisualState s{};s.raw_header_words[0]=0x02000006;s.raw_header_words[3]=clock;
    s.race_start_time=std::bit_cast<std::int32_t>(episode);s.position={1200,34,1360};s.input_gas=gas;return s;
}
int main()try{
    std::vector<std::optional<ReflectedVisualState>> copies{copy(100,200),copy(100,210),copy(100,220)};
    auto s=select_fresh_visual(copies);check(s&&s->clock_candidate_ms==220&&s->agreeing_copies==3,"Newest timestamp selection failed");
    copies={copy(100,400),copy(100,410),copy(300,420)};
    check(!select_fresh_visual(copies),"Previous episode falsely supplied quorum");
    copies={copy(0xffffffe0u,0xfffffff0u),copy(0x10,0x20),copy(0x10,0x30)};
    s=select_fresh_visual(copies);check(s&&s->clock_candidate_ms==0x30&&s->agreeing_copies==2,"Episode wrap-around failed");
    copies={copy(100,0xfffffff0u),copy(100,0x10),copy(100,0x20)};
    s=select_fresh_visual(copies);check(s&&s->clock_candidate_ms==0x20&&s->agreeing_copies==3,"Clock wrap-around failed");
    copies={copy(100,400,1),copy(100,900),copy(100,910)};
    s=select_fresh_visual(copies,std::nullopt,true);
    check(s&&s->clock_candidate_ms==910&&s->state.input_gas==0,"Stale throttle-on buffer shadowed coasting/braking");
    copies[0]=copy(100,890,1);s=select_fresh_visual(copies,std::nullopt,true);
    check(s&&s->clock_candidate_ms==890&&!s->authoritative_physics,"Bounded input-response preference failed");
    copies={copy(100,400),copy(100,410),copy(100,420)};copies[2]->raw_header_words[0]=0;
    check(!select_fresh_visual(copies),"Freed/non-visual buffer accepted");
    copies={copy(100,400),copy(100,410),copy(100,420)};
    copies[0]->position.x+=10;copies[1]->position.x-=10;
    check(!select_fresh_visual(copies),"Disagreeing vehicle copies supplied quorum");
    // Validate the inverse against the independently measured forward mapping,
    // including inner deadzone and signed seven-bit truncation.
    double max_error=0;
    for(int i=-1000;i<=1000;i++){
        const double desired=i/1000.;const auto raw=inverse_steering_deadzone(desired,.1);
        const double scaled=std::max(0.,(std::abs(raw)-.1)/.9);
        const double received=std::copysign(std::floor(scaled*127+1e-9)/127.,raw);
        max_error=std::max(max_error,std::abs(received-desired));
    }
    check(max_error<=.5/127.+1e-9,"Calibrated actuator exceeded half-bin error");
    check(inverse_steering_deadzone(0,.1)==0,"Neutral command crossed deadzone");
    check(tm2020::live_steer_from_raw(0)==0&&tm2020::live_steer_from_raw(127)==1&&
        tm2020::live_steer_from_raw(-127)==-1&&tm2020::live_steer_from_raw(-128)==-1,
        "Live raw-input normalization lost neutral or endpoints");
    for(double bad:{-.1,.9,std::numeric_limits<double>::quiet_NaN()}){
        bool rejected=false;try{(void)inverse_steering_deadzone(.2,bad);}catch(const std::invalid_argument&){rejected=true;}
        check(rejected,"Invalid actuator calibration accepted");
    }
    std::cout<<"PASS TELEMETRY episode_quorum=true timestamp_wrap=true stale_throttle_rejected=true actuator_max_error="<<max_error<<'\n';
}catch(const std::exception& e){std::cerr<<"TELEMETRY_TEST_ERROR "<<e.what()<<'\n';return 1;}

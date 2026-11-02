#pragma once
// Explicit map-specific reference feedforward + physical feedback + bounded NN.
// This is assisted trajectory tracking, not an unassisted generalist policy.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "internal_tick.hpp"

namespace tm2020::hybrid {
constexpr std::size_t features=12,hidden=32,weights=hidden*features+hidden+hidden+1,policy_weights=hidden*features+hidden+3*hidden+3;
struct Reference {std::array<float,25> data{};};
struct Cursor {std::uint32_t index{},last_ms{};bool started{};std::uint32_t drift_until_ms{};
    double filtered_feedback{};std::uint32_t feedback_ms{};bool feedback_started{},failed{};float previous_steer{};
    bool command_started{},previous_gas{},previous_brake{};std::uint32_t last_steer_change_ms{},last_gas_change_ms{},last_brake_change_ms{};
    int last_steer_delta{};std::array<std::uint32_t,100> steer_events{},fast_reversals{},small_reversals{},gas_events{},brake_events{};
    unsigned steer_event_count{},fast_reversal_count{},small_reversal_count{},gas_event_count{},brake_event_count{};
    unsigned total_steer_changes{},total_fast_reversals{},total_small_reversals{},total_pedal_transitions{};
    unsigned context_segment{};std::array<unsigned,4> segment_events{};};
class Tracker {
public:
    std::string uid,map_sha;
    std::uint32_t version{1}; // v2 preserves near-saturated teacher steering.
    std::array<double,6> gains{}; // lateral position/velocity, heading/yaw, phase bias, NN scale
    std::array<double,policy_weights> network{};
    // v3 filters only feedback. Human reference steering and pedals retain
    // their timing; there is no synthetic noise or replay modification.
    std::array<double,3> feedback_filter{}; // deadband, maximum step (0=off), interval ms
    // v5 action-space envelope: max per-tick i8 step, rolling 1s steer-change /
    // rapid-reversal / small-reversal budgets, minimum holds, pedal transition
    // budget and per-pedal minimum holds, and maximum absolute i8 steer.
    std::array<double,9> human_constraints{};
    std::array<double,13> human_envelope{};
    std::array<double,29> contextual_envelope{};
    std::vector<Reference> reference;
    // A control budget is an explicit neutral stop, never proof of arrival.
    bool budget_expired(const Cursor& cursor,std::uint32_t ms)const noexcept{
        return !reference.empty()&&cursor.started&&cursor.index+10>=reference.size()&&
            ms>=reference.size()*10+(version>=4?6000:40);
    }
    static std::uint64_t checksum(const unsigned char* p,std::size_t n){
        std::uint64_t h=14695981039346656037ull;
        for(std::size_t i=0;i<n;++i){h^=p[i];h*=1099511628211ull;}return h;
    }
    static Tracker load(const std::filesystem::path& path){
        std::ifstream file(path,std::ios::binary|std::ios::ate);
        if(!file||file.tellg()<64||file.tellg()>4*1024*1024)throw std::runtime_error("Invalid hybrid asset size");
        std::vector<unsigned char> bytes(static_cast<std::size_t>(file.tellg()));file.seekg(0);
        if(!file.read(reinterpret_cast<char*>(bytes.data()),bytes.size()))throw std::runtime_error("Hybrid asset read failed");
        std::uint64_t stored{};std::memcpy(&stored,bytes.data()+bytes.size()-8,8);
        if(std::memcmp(bytes.data(),"TMHYB001",8)||checksum(bytes.data(),bytes.size()-8)!=stored)
            throw std::runtime_error("Hybrid asset signature/checksum rejected");
        std::size_t offset=8;
        auto u32=[&](){std::uint32_t v{};if(offset+4>bytes.size()-8)throw std::runtime_error("Truncated hybrid header");std::memcpy(&v,bytes.data()+offset,4);offset+=4;return v;};
        const auto version=u32(),count=u32(),nx=u32(),nh=u32(),nu=u32(),ns=u32();
        if((version<1||version>8)||count<100||count>10000||nx!=features||nh!=hidden||nu<1||nu>64||ns!=64)
            throw std::runtime_error("Unsupported hybrid schema");
        const auto extra=version==3?3u:version==5?12u:version==6?16u:(version==7||version==8)?32u:0u;
        const auto net=version==8?policy_weights:weights;
        if(offset+nu+ns+(6+net+extra)*8+count*25*4!=bytes.size()-8)throw std::runtime_error("Hybrid lengths differ");
        Tracker t;t.version=version;t.uid.assign(reinterpret_cast<const char*>(bytes.data()+offset),nu);offset+=nu;
        t.map_sha.assign(reinterpret_cast<const char*>(bytes.data()+offset),ns);offset+=ns;
        std::memcpy(t.gains.data(),bytes.data()+offset,6*8);offset+=6*8;
        std::memcpy(t.network.data(),bytes.data()+offset,net*8);offset+=net*8;
        if(version==3||version==5||version==6||version==7||version==8){
            std::memcpy(t.feedback_filter.data(),bytes.data()+offset,24);offset+=24;
            const auto& f=t.feedback_filter;
            if(!std::isfinite(f[0])||f[0]<0||f[0]>8./127.||!std::isfinite(f[1])||f[1]<0||f[1]>1.||
               !std::isfinite(f[2])||f[2]<10||f[2]>50||std::fmod(f[2],10.)!=0)
                throw std::runtime_error("Invalid feedback filter");
        }
        if(version==5){
            std::memcpy(t.human_constraints.data(),bytes.data()+offset,72);offset+=72;
            const auto& c=t.human_constraints;
            if(!std::isfinite(c[0])||c[0]<1||c[0]>254||!std::isfinite(c[1])||c[1]<1||c[1]>100||
               !std::isfinite(c[2])||c[2]<0||c[2]>100||!std::isfinite(c[3])||c[3]<0||c[3]>100||
               !std::isfinite(c[4])||c[4]<10||c[4]>1000||!std::isfinite(c[5])||c[5]<1||c[5]>100||
               !std::isfinite(c[6])||c[6]<10||c[6]>5000||!std::isfinite(c[7])||c[7]<10||c[7]>5000||
               !std::isfinite(c[8])||c[8]<1||c[8]>127)
                throw std::runtime_error("Invalid human action envelope");
            for(double v:c)if(std::floor(v)!=v)throw std::runtime_error("Noninteger human action limit");
        }
        if(version==6){
            std::memcpy(t.human_envelope.data(),bytes.data()+offset,104);offset+=104;
            for(double v:t.human_envelope)if(!std::isfinite(v)||v<0||v>10000||std::floor(v)!=v)throw std::runtime_error("Invalid human action envelope value");
            for(unsigned i=9;i<13;++i)if(t.human_envelope[i]<1)throw std::runtime_error("Invalid human whole-run action budget");
            std::copy_n(t.human_envelope.begin(),9,t.human_constraints.begin());
            const auto& c=t.human_constraints;
            if(c[0]>254||c[1]>100||c[2]>100||c[3]>100||c[4]>1000||c[5]>100||c[6]>5000||c[7]>5000||c[8]>127)
                throw std::runtime_error("Invalid rolling human action envelope");
        }
        if(version==7||version==8){
            std::memcpy(t.contextual_envelope.data(),bytes.data()+offset,232);offset+=232;
            for(double v:t.contextual_envelope)if(!std::isfinite(v)||v<0||v>10000||std::floor(v)!=v)throw std::runtime_error("Invalid contextual human envelope");
            std::copy_n(t.contextual_envelope.begin(),9,t.human_constraints.begin());
            const auto& c=t.human_constraints;
            if(c[0]<1||c[0]>254||c[1]<1||c[1]>100||c[2]>100||c[3]>100||c[4]<10||c[4]>1000||
               c[5]<1||c[5]>100||c[6]<10||c[6]>5000||c[7]<10||c[7]>5000||c[8]<1||c[8]>127)
                throw std::runtime_error("Invalid rolling human action envelope");
            for(unsigned i=9;i<29;++i)if(t.contextual_envelope[i]<1)throw std::runtime_error("Invalid route-local action budget");
        }
        t.reference.resize(count);std::memcpy(t.reference.data(),bytes.data()+offset,count*25*4);
        for(double v:t.gains)if(!std::isfinite(v)||std::abs(v)>100.)throw std::runtime_error("Invalid hybrid gains");
        const bool valid_v8_mode=t.version==8&&t.gains[5]==-1.;
        if(t.gains[4]<0||(!valid_v8_mode&&(t.gains[5]<0||t.gains[5]>.25)))throw std::runtime_error("Invalid hybrid phase/residual limit");
        for(double v:t.network)if(!std::isfinite(v)||std::abs(v)>1e4)throw std::runtime_error("Invalid hybrid NN");
        for(const auto& r:t.reference){
            for(float v:r.data)if(!std::isfinite(v)||std::abs(v)>100000)throw std::runtime_error("Invalid hybrid reference");
            if(!internal::valid(internal::Controls{r.data[22],r.data[23],r.data[24]}))throw std::runtime_error("Invalid reference controls");
        }return t;
    }
    bool observation(Cursor& cursor,const float* state,std::uint32_t ms,std::array<double,features>& x,float& feedforward)const noexcept{
        if(reference.empty()||ms>(reference.size()+(version>=4?600:200))*10)return false;
        for(int k=0;k<22;++k)if(!std::isfinite(state[k])||std::abs(state[k])>100000)return false;
        if(cursor.started&&(ms<cursor.last_ms||ms-cursor.last_ms>100))return false;
        std::size_t index{};
        if(ms<200)index=std::min<std::size_t>(ms/10,reference.size()-1);
        else {
            const auto predicted=std::min<std::size_t>(cursor.index+(cursor.started?(ms-cursor.last_ms)/10:ms/10),reference.size()-1);
            const std::size_t behind=version==8?60:12,ahead=version==8?80:20;
            const auto lo=predicted>behind?predicted-behind:0,hi=std::min<std::size_t>(predicted+ahead,reference.size()-1);
            double best=1e100;index=predicted;
            for(std::size_t i=lo;i<=hi;++i){const auto& r=reference[i].data;double cost{};
                for(int k=0;k<3;++k){const double d=double(state[9+k])-r[9+k];cost+=d*d;}
                const double phase=double(i)-double(predicted);cost+=gains[4]*phase*phase;
                if(cost<best){best=cost;index=i;}
            }
        }
        const auto& r=reference[index].data;double ex{},ez{},ey{},vx{},vz{},heading{},yaw{},distance{};
        for(int k=0;k<3;++k){
            const double dp=double(state[9+k])-r[9+k],dv=double(state[16+k])-r[16+k];
            ex+=dp*r[k*3];ey+=dp*r[k*3+1];ez+=dp*r[k*3+2];
            vx+=dv*r[k*3];vz+=dv*r[k*3+2];heading+=double(state[k*3+2])*r[k*3];
            yaw+=(double(state[19+k])-r[19+k])*r[k*3+1];distance+=dp*dp;
        }
        if(distance>(version==8?400.:144.))return false;
        double speed{};for(int k=0;k<3;++k)speed+=double(state[16+k])*state[16+k];
        x={ex/5.,vx/20.,heading,yaw/5.,ez/10.,vz/20.,ey/5.,std::sqrt(speed)/100.,
           double(r[24]),double(index)/double(reference.size()-1),
           double(r[16])*r[2]/100.+double(r[17])*r[5]/100.+double(r[18])*r[8]/100.,1.};
        for(auto& v:x)v=std::clamp(v,-4.,4.);
        feedforward=r[24];cursor.index=static_cast<std::uint32_t>(index);cursor.last_ms=ms;cursor.started=true;return true;
    }
    double residual(const std::array<double,features>& x)const noexcept{
        double y=network[weights-1];
        for(std::size_t h=0;h<hidden;++h){double z=network[hidden*features+h];
            for(std::size_t j=0;j<features;++j)z+=network[h*features+j]*x[j];
            y+=network[hidden*features+hidden+h]*std::tanh(z);
        }return gains[5]*std::tanh(y);
    }
    std::array<double,3> policy(const std::array<double,features>& x)const noexcept{
        std::array<double,hidden> h{};
        for(std::size_t j=0;j<hidden;++j){double z=network[hidden*features+j];
            for(std::size_t k=0;k<features;++k)z+=network[j*features+k]*x[k];h[j]=std::tanh(z);}
        std::array<double,3> out{};
        constexpr std::size_t head=hidden*features+hidden;
        for(std::size_t a=0;a<3;++a){double z=network[head+3*hidden+a];
            for(std::size_t j=0;j<hidden;++j)z+=network[head+a*hidden+j]*h[j];out[a]=z;}
        return out;
    }
    template<std::size_t N> static void expire(std::array<std::uint32_t,N>& events,unsigned& count,std::uint32_t ms)noexcept{
        unsigned kept{};for(unsigned i=0;i<count;++i)if(ms-events[i]<1000)events[kept++]=events[i];count=kept;
    }
    template<std::size_t N> static void record(std::array<std::uint32_t,N>& events,unsigned& count,std::uint32_t ms)noexcept{
        if(count<N)events[count++]=ms;else{for(std::size_t i=1;i<N;++i)events[i-1]=events[i];events[N-1]=ms;}
    }
    void constrain(Cursor& q,std::uint32_t ms,internal::Controls& c)const noexcept{
        const auto& lim=human_constraints;
        if(!q.command_started){q.previous_steer=c.steer;q.previous_gas=c.gas>0.5f;q.previous_brake=c.brake>0.5f;
            q.last_steer_change_ms=q.last_gas_change_ms=q.last_brake_change_ms=ms;q.command_started=true;return;}
        expire(q.steer_events,q.steer_event_count,ms);expire(q.fast_reversals,q.fast_reversal_count,ms);
        expire(q.small_reversals,q.small_reversal_count,ms);expire(q.gas_events,q.gas_event_count,ms);expire(q.brake_events,q.brake_event_count,ms);
        const int previous=static_cast<int>(std::lround(q.previous_steer*127.f));
        int requested=static_cast<int>(std::lround(std::clamp(c.steer,-1.f,1.f)*127.f));
        requested=std::clamp(requested,-static_cast<int>(lim[8]),static_cast<int>(lim[8]));
        requested=std::clamp(requested,previous-static_cast<int>(lim[0]),previous+static_cast<int>(lim[0]));
        int delta=requested-previous;bool change=delta!=0;
        const bool too_soon=ms-q.last_steer_change_ms<static_cast<std::uint32_t>(lim[4]);
        const bool over_budget=q.steer_event_count>=static_cast<unsigned>(lim[1]);
        const bool reversal=change&&q.last_steer_delta!=0&&((q.last_steer_delta<0)!=(delta<0))&&ms-q.last_steer_change_ms<=100;
        const bool small=reversal&&std::abs(q.last_steer_delta)<=2&&std::abs(delta)<=2;
        unsigned segment=q.context_segment;
        if(version>=7){
            const auto phase=q.started?q.index:ms/10;
            const unsigned wanted=std::min(4u,static_cast<unsigned>(std::uint64_t(phase)*5/std::max<std::size_t>(reference.size(),1)));
            segment=std::max(q.context_segment,wanted);
            if(segment!=q.context_segment){q.context_segment=segment;q.segment_events={};}
        }
        const unsigned segment_offset=9+segment*4;
        const bool run_steer_exhausted=version==6&&q.total_steer_changes>=static_cast<unsigned>(human_envelope[9]);
        const bool run_reversal_exhausted=version==6&&reversal&&q.total_fast_reversals>=static_cast<unsigned>(human_envelope[10]);
        const bool run_small_exhausted=version==6&&small&&q.total_small_reversals>=static_cast<unsigned>(human_envelope[11]);
        const bool segment_steer_exhausted=version>=7&&q.segment_events[0]>=static_cast<unsigned>(contextual_envelope[segment_offset]);
        const bool segment_reversal_exhausted=version>=7&&reversal&&q.segment_events[1]>=static_cast<unsigned>(contextual_envelope[segment_offset+1]);
        const bool segment_small_exhausted=version>=7&&small&&q.segment_events[2]>=static_cast<unsigned>(contextual_envelope[segment_offset+2]);
        if(change&&(too_soon||over_budget||(reversal&&q.fast_reversal_count>=static_cast<unsigned>(lim[2]))||
                    (small&&q.small_reversal_count>=static_cast<unsigned>(lim[3]))||run_steer_exhausted||run_reversal_exhausted||run_small_exhausted||
                    segment_steer_exhausted||segment_reversal_exhausted||segment_small_exhausted)){requested=previous;delta=0;change=false;}
        if(change){record(q.steer_events,q.steer_event_count,ms);if(reversal)record(q.fast_reversals,q.fast_reversal_count,ms);
            if(small)record(q.small_reversals,q.small_reversal_count,ms);++q.total_steer_changes;if(reversal)++q.total_fast_reversals;if(small)++q.total_small_reversals;
            if(version>=7){++q.segment_events[0];if(reversal)++q.segment_events[1];if(small)++q.segment_events[2];}
            q.last_steer_change_ms=ms;q.last_steer_delta=delta;}
        c.steer=static_cast<float>(requested)/127.f;
        auto pedal=[&](bool wanted,bool& previous_value,std::uint32_t& last_change,
                       std::array<std::uint32_t,100>& events,unsigned& count,std::uint32_t min_hold,float& output){
            bool value=wanted;if(value!=previous_value){
                if(ms-last_change<min_hold||count>=static_cast<unsigned>(lim[5])||
                   (version==6&&q.total_pedal_transitions>=static_cast<unsigned>(human_envelope[12]))||
                   (version>=7&&q.segment_events[3]>=static_cast<unsigned>(contextual_envelope[segment_offset+3])))value=previous_value;
                else{record(events,count,ms);last_change=ms;previous_value=value;if(version==6)++q.total_pedal_transitions;if(version>=7)++q.segment_events[3];}
            }output=value?1.f:0.f;
        };
        pedal(c.gas>0.5f,q.previous_gas,q.last_gas_change_ms,q.gas_events,q.gas_event_count,
              static_cast<std::uint32_t>(lim[6]),c.gas);
        pedal(c.brake>0.5f,q.previous_brake,q.last_brake_change_ms,q.brake_events,q.brake_event_count,
              static_cast<std::uint32_t>(lim[7]),c.brake);
    }
    bool action(Cursor& cursor,const float* rigid,std::uint32_t ms,internal::Controls& controls,
                std::array<double,features>* output=nullptr,double extra_residual=0.)const noexcept{
        std::array<double,features> x{};float ff{};
        if(cursor.failed){controls={};if(output)*output=x;return false;}
        if(budget_expired(cursor,ms)){controls={};if(output)*output=x;return true;}
        if(!observation(cursor,rigid,ms,x,ff)){cursor.failed=true;controls={};return false;}
        // v4 is learned feedback on genuine normal input history. Give the
        // actor actual previous steering and upcoming human steering context.
        // No post-action filter. Old versions keep their observation schema.
        if(version==4||version==5||version==6||version==7){x[8]=cursor.previous_steer;x[9]=ff;
            x[10]=reference[std::min<std::size_t>(cursor.index+10,reference.size()-1)].data[24];}
        if(version==8){
            x[8]=gains[5]<0.?0.:cursor.previous_steer;
            const auto& here=reference[cursor.index].data;
            const auto& ahead=reference[std::min<std::size_t>(cursor.index+10,reference.size()-1)].data;
            const double h0=std::atan2(double(here[2]),double(here[8]));
            const double h1=std::atan2(double(ahead[2]),double(ahead[8]));
            x[10]=std::clamp(std::remainder(h1-h0,6.2831853071795864769)*10.,-4.,4.);
        }
        if(version==8){
            const auto logits=policy(x);
            const double delta_scale=gains[5]==0.?1.:gains[5];
            const double steer_target=gains[5]<0.?std::tanh(logits[0]):
                x[8]+delta_scale*std::tanh(logits[0]);
            const float steer=static_cast<float>(std::clamp(steer_target,-1.,1.));
            controls={logits[1]>=0.?1.f:0.f,logits[2]>=0.?1.f:0.f,steer};
            if(!internal::valid(controls)){cursor.failed=true;controls={};return false;}
            constrain(cursor,ms,controls);cursor.previous_steer=controls.steer;
            if(output)*output=x;return true;
        }
        double correction=-gains[0]*x[0]*5.-gains[1]*x[1]*20.-gains[2]*x[2]-gains[3]*x[3]*5.+residual(x)+extra_residual;
        if(!std::isfinite(correction)){cursor.failed=true;controls={};return false;}
        if(version==3||version==5||version==6||version==7){
            if(!cursor.feedback_started||ms-cursor.feedback_ms>=feedback_filter[2]){
                const double previous=cursor.filtered_feedback;
                if(std::abs(correction)<=feedback_filter[0])correction=0.;
                if(std::abs(correction-previous)>feedback_filter[0]||correction==0.){
                    if(feedback_filter[1]>0)correction=std::clamp(correction,previous-feedback_filter[1],previous+feedback_filter[1]);
                    cursor.filtered_feedback=correction;
                }
                cursor.feedback_ms=ms;cursor.feedback_started=true;
            }
            correction=cursor.filtered_feedback;
        }
        double steer=double(ff)+correction;
        // Explicit opt-in: preserve saturation during a brake-initiated drift,
        // rather than forcing it during unrelated full-steering corners.
        if(reference[cursor.index].data[23]==1.f)cursor.drift_until_ms=ms+700;
        if(version==2&&ms<cursor.drift_until_ms&&std::abs(ff)>=125.f/127.f)steer=ff;
        if(!std::isfinite(steer)){cursor.failed=true;controls={};return false;}
        const auto& target=reference[cursor.index].data;
        const float s=static_cast<float>(std::clamp(steer,-1.,1.));controls={target[22],target[23],std::round(s*127.f)/127.f};
        if(version==5||version==6||version==7)constrain(cursor,ms,controls);
        cursor.previous_steer=controls.steer;
        if(output)*output=x;return true;
    }
};
}

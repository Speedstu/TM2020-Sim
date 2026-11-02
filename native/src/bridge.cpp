// Trackmania 2020 C++ native execution ABI for offline research.
// Does NOT inject into Trackmania, patch its code or bypass protections.
// Caller must supply trusted offline-only observations from a yet-to-be-
// validated game state adapter. Actions are ADVISORY unless caller applies them.
#define TM2020_BRIDGE_BUILD
#include "tm2020/bridge.h"
#include "tm2020.hpp"
#include "tm2020/route_controller.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <string>

namespace {
std::mutex lock;
std::unique_ptr<tm2020::RoutePlan> route;
std::optional<tm2020::BCPolicy> policy;
uint32_t activeMode=TM2020_BRIDGE_OBSERVE_ONLY;
uint64_t prevTick=0;
bool hasTick=false;
double lookahead=25.0;
double pursuitGain=0.0;
thread_local std::string error;
void setError(const char* text){error=text;}
bool finite_value(double x){return std::isfinite(x);}
bool valid(const tm2020_bridge_observation& a){
    if(!finite_value(a.heading_rad)||!finite_value(a.speed_kmh)||!finite_value(a.side_speed)||a.reserved_zero||
       a.speed_kmh<0||a.speed_kmh>2000) return false;
    for(int i=0;i<3;i++){
        if(!finite_value(a.world_position_xyz[i])||!finite_value(a.world_velocity_xyz[i]))
            return false;
    }
    return true;
}
void neutral(tm2020_bridge_action* out,uint64_t tick){
    std::memset(out,0,sizeof(*out));
    out->size_bytes=sizeof(*out);
    out->api_version=TM2020_BRIDGE_API_VERSION;
    out->observation_tick=tick;
}
}
extern "C" {
uint32_t tm2020_bridge_version(void) {return TM2020_BRIDGE_API_VERSION;}
const char* tm2020_bridge_last_error(void){return error.c_str();}
void tm2020_bridge_shutdown(void){
    std::lock_guard<std::mutex> guard(lock);
    route.reset();
    policy.reset();
    activeMode=TM2020_BRIDGE_OBSERVE_ONLY;
    pursuitGain=0.0;
    hasTick=false;
    error.clear();
}
int32_t tm2020_bridge_init(const tm2020_bridge_config* conf) {
    if(!conf||conf->size_bytes!=sizeof(*conf)||conf->api_version!=TM2020_BRIDGE_API_VERSION||
       conf->reserved_zero||conf->mode>TM2020_BRIDGE_LOCAL_REFERENCE_FOLLOWER||
       !conf->replay_tmreplay_utf8||!conf->replay_tmreplay_utf8[0]||
       !finite_value(conf->lookahead_m)||conf->lookahead_m<1||conf->lookahead_m>300||
       !finite_value(conf->heading_gain)||std::abs(conf->heading_gain)>100 ||
       (conf->mode==TM2020_BRIDGE_LOCAL_REFERENCE_FOLLOWER &&
        (conf->lookahead_m<2||conf->lookahead_m>200||std::abs(conf->heading_gain)<1e-9))) {
        setError("Invalid ABI config/unsupported version/lookahead");
        return TM2020_BRIDGE_E_BAD_ARGUMENT;
    }
    try{
        const auto replay=tm2020::Replay::load(conf->replay_tmreplay_utf8);
        auto newRoute=std::make_unique<tm2020::RoutePlan>(replay);
        std::optional<tm2020::BCPolicy> newPolicy;
        if(conf->mode==TM2020_BRIDGE_LOCAL_DEMONSTRATION){
            if(!conf->policy_tmbc_utf8||!conf->policy_tmbc_utf8[0]){
                setError("Local demonstration requires an explicit BC model path");
                return TM2020_BRIDGE_E_BAD_ARGUMENT;
            }
            newPolicy=tm2020::BCPolicy::load(conf->policy_tmbc_utf8);
        }
        std::lock_guard<std::mutex> guard(lock);
        policy=std::move(newPolicy);
        route=std::move(newRoute);
        activeMode=conf->mode;
        lookahead=conf->lookahead_m;
        pursuitGain=conf->heading_gain;
        hasTick=false;
        error.clear();
        return TM2020_BRIDGE_OK;
    }catch(const std::exception& e){
        setError(e.what());return TM2020_BRIDGE_E_LOAD;
    }catch(...){
        setError("Unhandled error reading runtime data");return TM2020_BRIDGE_E_LOAD;
    }
}
int32_t tm2020_bridge_sample(const tm2020_bridge_observation* obs,tm2020_bridge_action* out){
    if(!obs||!out||obs->size_bytes!=sizeof(*obs)||
       obs->api_version!=TM2020_BRIDGE_API_VERSION||
       out->size_bytes!=sizeof(*out)||out->api_version!=TM2020_BRIDGE_API_VERSION){
        setError("Invalid ABI observation/action structure size");
        return TM2020_BRIDGE_E_BAD_ARGUMENT;
    }
    neutral(out,obs->tick_index);
    if(!obs->is_local_offline){
        setError("Local/offline-only policy: online observations are never actuated");
        return TM2020_BRIDGE_E_NOT_LOCAL;
    }
    if(!obs->is_valid_race_state){
        setError("No valid race state");
        return TM2020_BRIDGE_E_BAD_STATE;
    }
    if(!valid(*obs)){
        setError("Non-finite or out-of-range vehicle observation");
        return TM2020_BRIDGE_E_BAD_STATE;
    }
    try{
        std::lock_guard<std::mutex> guard(lock);
        if(!route){
            setError("Initialize the bridge before sampling");
            return TM2020_BRIDGE_E_NOT_INITIALIZED;
        }
        if(hasTick && obs->tick_index<=prevTick){
            setError("Stale or duplicate observation tick");
            return TM2020_BRIDGE_E_BAD_STATE;
        }
        tm2020::State current;
        current.time_ms=0; // Unused in RoutePlan/BC feature inference.
        current.position={obs->world_position_xyz[0],obs->world_position_xyz[1],
                          obs->world_position_xyz[2]};
        current.velocity={obs->world_velocity_xyz[0],obs->world_velocity_xyz[1],
                          obs->world_velocity_xyz[2]};
        current.yaw_rad=obs->heading_rad;
        current.speed_kmh=obs->speed_kmh;
        current.side_speed=obs->side_speed;
        current.ground_contact=obs->ground_contact!=0;
        for(int wheel=0;wheel<4;wheel++)current.contact_materials[wheel]=obs->wheel_contact_materials[wheel];
        const auto target=route->target(current.position,current.yaw_rad,lookahead);
        out->route_lookahead_m=target.distance_ahead_m;
        out->distance_from_reference_m=target.lateral_error_m;
        if(activeMode==TM2020_BRIDGE_LOCAL_DEMONSTRATION && policy.has_value()){
            const auto future=route->as_desired_future(current,lookahead);
            const auto cmd=policy->predict(current,future);
            // No game input is sent by this library.
            out->steer=cmd.steer;
            out->throttle=cmd.gas;
            out->brake=cmd.brake;
            out->active=1;
        } else if(activeMode==TM2020_BRIDGE_LOCAL_REFERENCE_FOLLOWER){
            const auto action=tm2020::propose_reference_controls(
                *route,current,{lookahead,pursuitGain});
            out->steer=action.steer;
            out->throttle=action.gas;
            out->brake=action.brake;
            out->active=1;
        }
        hasTick=true;
        prevTick=obs->tick_index;
        error.clear();
        return TM2020_BRIDGE_OK;
    }catch(const std::exception& e){
        neutral(out,obs->tick_index);
        setError(e.what());return TM2020_BRIDGE_E_BAD_STATE;
    }catch(...){
        neutral(out,obs->tick_index);
        setError("Unexpected native bridge error");return TM2020_BRIDGE_E_BAD_STATE;
    }
}
}

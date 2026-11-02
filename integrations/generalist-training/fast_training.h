#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define TMFAST_OBSERVATIONS 48
#define TMFAST_API_VERSION 4
#define TMFAST_SCHEMA "tm2020_generalist48_v1|controls=binary_pedals_i8_steer|perception=static_rays33_goal_aabb_v1"
#define TMFAST_SCHEMA_100HZ "tm2020_generalist48_100hz_v1|controls=binary_pedals_i8_steer|perception=static_rays33_goal_aabb_v1"
#define TMFAST_PREVIEW_SCHEMA "tm2020_preview72_v1|controls=binary_pedals_i8_steer|perception=static_goal_preview_omega_v1"
#define TMFAST_PLANNER_SCHEMA "unsupported_planner"
typedef void* tmfast_env;
typedef struct tmfast_state {
    double observation[TMFAST_OBSERVATIONS];
    double reward,progress,cross_track,speed;
    uint32_t rigid_words[22];
    uint32_t tick,checkpoints,terminated,truncated,advanced_ticks;
    int32_t finish_ms;
    float controls[3]; /* gas, brake, steer, applied to physics */
    uint32_t reserved;
} tmfast_state;
uint32_t tmfast_version(void);
uint32_t tmfast_bank_size(tmfast_env env);
const char* tmfast_last_error(void);
tmfast_env tmfast_open(const char* map,const char* packs,const char* route_replay,uint32_t horizon);
tmfast_env tmfast_clone(tmfast_env env);
int32_t tmfast_configure(tmfast_env env,double lookahead,double gain,double residual);
int32_t tmfast_configure_planner(tmfast_env env,uint32_t enabled);
int32_t tmfast_reset(tmfast_env env,uint32_t seed,tmfast_state* state);
int32_t tmfast_reset_bank(tmfast_env env,uint32_t seed,uint32_t bank,tmfast_state* state);
int32_t tmfast_step(tmfast_env env,const double* action,uint32_t repeat,tmfast_state* state);
int32_t tmfast_step_controls(tmfast_env env,const float* gas_brake_steer,uint32_t repeat,tmfast_state* state);
void tmfast_close(tmfast_env env);
#ifdef __cplusplus
}
#endif

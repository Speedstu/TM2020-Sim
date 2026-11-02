#pragma once
/* Native PPO collection/training for external environment adapters.
 * Environment fidelity and reward semantics belong to the caller. A sampled
 * decision is committed only after a valid successor observation. Cancel a
 * pending decision after an environment failure; it never becomes a row.
 * Handles require exclusive ownership, including close. No game access.
 */
#include "policy.h"
#ifdef __cplusplus
extern "C" {
#endif
#define TM2020_TRAINER_API_VERSION 1u
typedef void* tm2020_trainer_handle;
typedef struct tm2020_trainer_metrics {
    uint32_t size_bytes,api_version;
    uint64_t transitions,optimizer_steps,minibatches,epochs;
    double policy_loss,value_loss,approx_kl,clip_fraction,gradient_norm;
    uint32_t kl_stopped,reserved_zero;
} tm2020_trainer_metrics;
TM2020_POLICY_EXPORT uint32_t tm2020_trainer_version(void);
TM2020_POLICY_EXPORT int32_t tm2020_trainer_create(uint32_t observations,
    uint32_t actions,uint32_t width,uint64_t seed,const char* schema,
    tm2020_trainer_handle* out);
TM2020_POLICY_EXPORT int32_t tm2020_trainer_sample(tm2020_trainer_handle handle,
    const double* observations,uint32_t observation_count,
    double* actions,uint32_t action_count,double* value);
TM2020_POLICY_EXPORT int32_t tm2020_trainer_observe(tm2020_trainer_handle handle,
    double reward,const double* successor,uint32_t observation_count,
    uint32_t terminated,uint32_t truncated,double elapsed_steps);
/* Discard pending action and truncate the last accepted row, preserving its
 * already observed successor bootstrap. No fabricated terminal or reward. */
TM2020_POLICY_EXPORT int32_t tm2020_trainer_cancel(tm2020_trainer_handle handle);
TM2020_POLICY_EXPORT int32_t tm2020_trainer_update(tm2020_trainer_handle handle,
    tm2020_trainer_metrics* metrics);
/* Export accepted observations/latents/likelihoods/values before updating. */
TM2020_POLICY_EXPORT int32_t tm2020_trainer_rollout_csv(tm2020_trainer_handle handle,const char* path_utf8);
/* Checkpoints include weights, Adam, configuration, shuffle and sampler RNGs.
 * Checkpoint/export/load require an empty rollout and no pending decision. */
TM2020_POLICY_EXPORT int32_t tm2020_trainer_checkpoint(tm2020_trainer_handle handle,const char* path_utf8);
TM2020_POLICY_EXPORT int32_t tm2020_trainer_resume(tm2020_trainer_handle handle,const char* path_utf8);
TM2020_POLICY_EXPORT int32_t tm2020_trainer_export(tm2020_trainer_handle handle,const char* path_utf8);
TM2020_POLICY_EXPORT void tm2020_trainer_close(tm2020_trainer_handle handle);
TM2020_POLICY_EXPORT const char* tm2020_trainer_last_error(void);
#ifdef __cplusplus
}
#endif

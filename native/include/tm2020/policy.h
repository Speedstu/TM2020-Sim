#pragma once
/* Handle-based native PPO inference, callable from an ordinary or injected
 * host. Loading/injecting a DLL does not provide game hooks or physics state.
 * Independent of the existing game bridge ABI v3. Caller owns observations.
 */
#include <stdint.h>
#ifdef _WIN32
# ifdef TM2020_POLICY_BUILD
#  define TM2020_POLICY_EXPORT __declspec(dllexport)
# else
#  define TM2020_POLICY_EXPORT __declspec(dllimport)
# endif
#else
# define TM2020_POLICY_EXPORT
#endif
#ifdef __cplusplus
extern "C" {
#endif
#define TM2020_POLICY_API_VERSION 1u
typedef void* tm2020_policy_handle;
typedef struct tm2020_policy_info {
    uint32_t size_bytes,api_version,observation_count,action_count;
    uint32_t hidden_width,reserved_zero;
} tm2020_policy_info;
TM2020_POLICY_EXPORT uint32_t tm2020_policy_version(void);
TM2020_POLICY_EXPORT int32_t tm2020_policy_open(const char* model_utf8,tm2020_policy_handle* out);
TM2020_POLICY_EXPORT int32_t tm2020_policy_get_info(tm2020_policy_handle handle,tm2020_policy_info* out);
/* Returned schema is borrowed until close(). Compare it with the host's
 * observation encoder; dimension equality alone is insufficient. */
TM2020_POLICY_EXPORT const char* tm2020_policy_schema(tm2020_policy_handle handle);
TM2020_POLICY_EXPORT int32_t tm2020_policy_predict(tm2020_policy_handle handle,
    const double* observations,uint32_t observation_count,
    double* actions,uint32_t action_count,double* value);
/* Immutable handles allow concurrent predictions. Close requires exclusive
 * ownership: never close during another API call or reuse a closed handle. */
TM2020_POLICY_EXPORT void tm2020_policy_close(tm2020_policy_handle handle);
TM2020_POLICY_EXPORT const char* tm2020_policy_last_error(void);
#ifdef _WIN32
/* Loader qualification only: Windows thread-compatible, no game state access. */
TM2020_POLICY_EXPORT uint32_t __stdcall tm2020_policy_host_probe(void* reserved_zero);
#endif
#ifdef __cplusplus
}
#endif

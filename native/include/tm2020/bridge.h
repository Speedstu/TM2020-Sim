#pragma once
/* Trackmania2020 offline research: stable plugin ABI for C++ native execution.
 * NOTE: This SDK does not inject, hook or patch the game.
 * A separate, authorized offline state adapter must obtain reliable vehicle
 * state, which is NOT currently reverse engineered for TM2020 2026 builds.
 */
#include <stdint.h>
#ifdef _WIN32
  #ifdef TM2020_BRIDGE_BUILD
    #define TM2020_BRIDGE_EXPORT __declspec(dllexport)
  #else
    #define TM2020_BRIDGE_EXPORT __declspec(dllimport)
  #endif
#else
  #define TM2020_BRIDGE_EXPORT
#endif
#ifdef __cplusplus
extern "C" {
#endif
#define TM2020_BRIDGE_API_VERSION 3u
typedef enum tm2020_bridge_mode {
    TM2020_BRIDGE_OBSERVE_ONLY = 0,
    TM2020_BRIDGE_LOCAL_DEMONSTRATION = 1,
    TM2020_BRIDGE_LOCAL_REFERENCE_FOLLOWER = 2
} tm2020_bridge_mode;
typedef enum tm2020_bridge_status {
    TM2020_BRIDGE_OK = 0,
    TM2020_BRIDGE_E_BAD_ARGUMENT = -1,
    TM2020_BRIDGE_E_NOT_INITIALIZED = -2,
    TM2020_BRIDGE_E_NOT_LOCAL = -3,
    TM2020_BRIDGE_E_BAD_STATE = -4,
    TM2020_BRIDGE_E_LOAD = -5
} tm2020_bridge_status;
typedef struct tm2020_bridge_config {
    uint32_t size_bytes;
    uint32_t api_version;
    uint32_t mode;  /* 0=observe only; 1=BC demonstration; 2=pure-pursuit follower */
    uint32_t reserved_zero;
    const char* replay_tmreplay_utf8;
    const char* policy_tmbc_utf8;
    double lookahead_m;
    double heading_gain; /* Pure-pursuit mode only, bounded |gain|<=100. */
} tm2020_bridge_config;
typedef struct tm2020_bridge_observation {
    uint32_t size_bytes;
    uint32_t api_version;
    uint64_t tick_index;
    /* Must be provided by a trusted host running in an authorized LOCAL race.
     * The bridge cannot independently verify a game/server session. */
    uint32_t is_local_offline;
    uint32_t is_valid_race_state;
    double world_position_xyz[3];
    double world_velocity_xyz[3];
    double heading_rad;
    double speed_kmh;
    double side_speed;
    uint8_t wheel_contact_materials[4];
    uint32_t ground_contact;
    uint32_t reserved_zero;
} tm2020_bridge_observation;
typedef struct tm2020_bridge_action {
    uint32_t size_bytes;
    uint32_t api_version;
    uint32_t active; /* 0 = neutral/no actuation; 1 = advisory local action */
    uint32_t reserved_zero;
    double steer;
    double throttle;
    double brake;
    double route_lookahead_m;
    double distance_from_reference_m;
    uint64_t observation_tick;
} tm2020_bridge_action;
TM2020_BRIDGE_EXPORT int32_t tm2020_bridge_init(const tm2020_bridge_config* config);
TM2020_BRIDGE_EXPORT int32_t tm2020_bridge_sample(
    const tm2020_bridge_observation* observation, tm2020_bridge_action* action);
TM2020_BRIDGE_EXPORT void tm2020_bridge_shutdown(void);
TM2020_BRIDGE_EXPORT const char* tm2020_bridge_last_error(void);
TM2020_BRIDGE_EXPORT uint32_t tm2020_bridge_version(void);
#ifdef __cplusplus
}
#endif

#pragma once
/* Windows explicit-worker ABI 1. LoadLibrary alone never starts the bot.
 * tm2020_bot_run takes a bounded NUL-terminated absolute UTF-16 config path;
 * the caller owns that storage until the function returns. Worker runs on the
 * calling thread, requires an already selected local Solo race, and releases
 * its inputs before returning. Never call either entry from DllMain.
 */
#ifdef _WIN32
#include <Windows.h>
#ifdef TM2020_RUNTIME_BUILD
#define TM2020_RUNTIME_API __declspec(dllexport)
#else
#define TM2020_RUNTIME_API __declspec(dllimport)
#endif
#define TM2020_RUNTIME_ABI_VERSION 1
enum tm2020_runtime_result {
    TM2020_RUNTIME_OK=0,TM2020_RUNTIME_SESSION_FAILED=1,
    TM2020_RUNTIME_BUSY=2,TM2020_RUNTIME_INVALID_CONFIG=3,
    TM2020_RUNTIME_WRONG_PROCESS=4,TM2020_RUNTIME_LOCK_FAILED=5,
    TM2020_RUNTIME_INTERNAL_ERROR=6
};
#ifdef __cplusplus
#define TM2020_RUNTIME_NOEXCEPT noexcept
extern "C" {
#else
#define TM2020_RUNTIME_NOEXCEPT
#endif
/* Probe hashes the host executable; returns ABI 1 or zero on failure. */
TM2020_RUNTIME_API DWORD WINAPI tm2020_runtime_probe(void* must_be_null) TM2020_RUNTIME_NOEXCEPT;
TM2020_RUNTIME_API DWORD WINAPI tm2020_bot_run(void* absolute_utf16_config_path) TM2020_RUNTIME_NOEXCEPT;
#ifdef __cplusplus
}
#endif
#endif

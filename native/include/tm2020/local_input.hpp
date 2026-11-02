#pragma once
#include "tm2020.hpp"
#include <cstdint>
#include <filesystem>
#include <memory>
namespace tm2020::live {
enum class InputBackend { Keyboard, ViGEmXbox360 };
// Foreground-process-bound LOCAL SOLO controller. No game memory writes.
// A CLI/host must establish the local race context; PID alone cannot prove it.
class LocalInput {
public:
    LocalInput(std::uint32_t game_pid,InputBackend backend,
               const std::filesystem::path& vigem_client_dll={});
    ~LocalInput();
    LocalInput(const LocalInput&)=delete;
    LocalInput& operator=(const LocalInput&)=delete;
    void apply(Controls controls); // throws + neutralizes on focus/process loss
    void neutral() noexcept;
    void restart(); // normal Delete-key restart, real time; no snapshot claim
    void start_race(); // held Enter to dismiss the local Solo presentation
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}

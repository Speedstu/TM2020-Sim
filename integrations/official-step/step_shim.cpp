// SPDX-License-Identifier: MIT
// Build-128182 research adapter. The installed executable is never changed.
// Ownership offsets and call-site provenance: TAS 036a65b, VALIDATOR_CAR.md.
// Stop at the real decoded-input call, without fork() or a fitted clock.
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <link.h>
#include <signal.h>
#include <sys/mman.h>
#include <ucontext.h>
#include <unistd.h>

namespace {
uintptr_t image, controller, simulation;
bool observed_car;
int out_fd = -1, in_fd = -1;
int32_t engine_ms, origin_ms, start_offset_ms, tape_count;
constexpr uintptr_t bind_off = 0x118c18a;
constexpr uintptr_t input_off = 0x1219f89;
constexpr uintptr_t after_off = 0x1219f8e;
constexpr uintptr_t decode_off = 0x119f0f0;

// Little-endian fixed frames, no heap allocations or stdio in signal handlers.
struct Frame {
    uint32_t magic = 0x36304d54; // TM06
    int32_t engine_ms, origin_ms, start_offset_ms, tape_count, index;
    std::array<float, 3> controls; // steer, gas, brake (engine order)
    std::array<float, 10> state; // wxyz, xyz, linear velocity xyz
};
static_assert(sizeof(Frame) == 76);
struct Action { uint32_t mode; std::array<float, 3> controls; };
static_assert(sizeof(Action) == 16);

[[noreturn]] void fail(const char* message) {
    // Callers use string literals. strlen is resolved before any traps fire.
    write(STDERR_FILENO, message, std::strlen(message));
    _exit(86);
}
bool transfer(int fd, void* data, size_t size, bool sending) {
    auto* p = static_cast<uint8_t*>(data);
    while (size) {
        ssize_t n = sending ? write(fd, p, size) : read(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        p += n; size -= static_cast<size_t>(n);
    }
    return true;
}
template<class T> T load(uintptr_t p) {
    T value; std::memcpy(&value, reinterpret_cast<const void*>(p), sizeof(T));
    return value;
}
uintptr_t ptr(uintptr_t p) {
    auto result = load<uintptr_t>(p);
    if (result < 0x1000 || result >= 0x800000000000ULL)
        fail("official-step: invalid ownership pointer\n");
    return result;
}

void sample(uintptr_t participant) {
    if (!controller || ptr(controller + 0x1a70) != simulation)
        fail("official-step: validator simulation identity differs\n");
    auto playground = ptr(simulation + 0x18);
    if (load<uint32_t>(playground + 0x668) != 1)
        fail("official-step: validator player count differs\n");
    if (ptr(ptr(playground + 0x660)) != participant)
        fail("official-step: callback participant identity differs\n");
    if (load<uint32_t>(participant + 0x1110) != 0x032e2000) {
        if (observed_car) fail("official-step: controlled vehicle disappeared\n");
        return; // Before the initial vehicle is constructed; no frame/action.
    }
    observed_car = true;
    auto vehicle = ptr(participant + 0x1118);
    Frame frame;
    frame.engine_ms = engine_ms; frame.origin_ms = origin_ms;
    frame.start_offset_ms = start_offset_ms; frame.tape_count = tape_count;
    // Original decoder: 119f0fc..119f15b. Label the input actually read.
    int64_t relative = int64_t(engine_ms) - (int64_t(origin_ms) - 10) -
        (int64_t(start_offset_ms) + 10);
    frame.index = relative < 0 ? -1 : static_cast<int32_t>(relative / 10);
    // The 32-byte record starts with flags; normalized axes start at +4.
    frame.controls = load<std::array<float, 3>>(participant + 0x18c);
    frame.state = load<std::array<float, 10>>(vehicle + 0x12e0);
    for (float x : frame.state)
        if (!std::isfinite(x)) fail("official-step: nonfinite state\n");
    if (!transfer(out_fd, &frame, sizeof(frame), true)) _exit(0);
    if (in_fd >= 0) {
        Action action;
        if (!transfer(in_fd, &action, sizeof(action), false)) _exit(0);
        if (action.mode > 1) fail("official-step: invalid action mode\n");
        if (action.mode == 1) {
            if (frame.index < 0 || frame.index >= frame.tape_count)
                fail("official-step: override outside decoded tape\n");
            const auto& a = action.controls;
            if (!std::isfinite(a[0]) || !std::isfinite(a[1]) || !std::isfinite(a[2]) ||
                a[0] < -1 || a[0] > 1 || a[1] < 0 || a[1] > 1 || a[2] < 0 || a[2] > 1)
                fail("official-step: invalid normalized action\n");
            std::memcpy(reinterpret_cast<void*>(participant + 0x18c), a.data(), 12);
        }
    }
}

void trap(int, siginfo_t*, void* context) {
    auto& r = static_cast<ucontext_t*>(context)->uc_mcontext.gregs;
    uintptr_t at = uintptr_t(r[REG_RIP]) - 1;
    if (at == image + bind_off) {
        controller = r[REG_RDI]; simulation = r[REG_RCX];
        // Emulate mov [rdi+0x1a70],rcx. Neither mov nor call changes flags.
        std::memcpy(reinterpret_cast<void*>(controller + 0x1a70), &simulation, 8);
        r[REG_RIP] = at + 7;
    } else if (at == image + input_off) {
        engine_ms = static_cast<int32_t>(r[REG_RDI]);
        origin_ms = static_cast<int32_t>(r[REG_RSI]);
        start_offset_ms = static_cast<int32_t>(r[REG_R8]);
        tape_count = static_cast<int32_t>(r[REG_RCX]);
        // Emulate the original relative call, retaining its stack argument.
        uintptr_t ret = image + after_off;
        r[REG_RSP] -= 8;
        std::memcpy(reinterpret_cast<void*>(r[REG_RSP]), &ret, 8);
        r[REG_RIP] = image + decode_off;
    } else if (at == image + after_off) {
        sample(r[REG_R13]);
        // Emulate mov dword ptr [r13+0x374],0, exactly eleven bytes.
        uint32_t zero = 0;
        std::memcpy(reinterpret_cast<void*>(r[REG_R13] + 0x374), &zero, 4);
        r[REG_RIP] = at + 11;
    } else {
        fail("official-step: unexpected trap\n");
    }
}
int module(dl_phdr_info* info, size_t, void*) {
    if (!info->dlpi_name || !*info->dlpi_name) { image = info->dlpi_addr; return 1; }
    return 0;
}
template<size_t N> void patch(uintptr_t offset, const std::array<uint8_t, N>& bytes) {
    auto at = image + offset;
    if (std::memcmp(reinterpret_cast<void*>(at), bytes.data(), N))
        fail("official-step: unsupported instruction signature\n");
    auto page = at & ~uintptr_t(getpagesize() - 1);
    if (mprotect(reinterpret_cast<void*>(page), getpagesize(), PROT_READ|PROT_WRITE|PROT_EXEC))
        fail("official-step: cannot install owned-process hook\n");
    *reinterpret_cast<volatile uint8_t*>(at) = 0xcc;
    if (mprotect(reinterpret_cast<void*>(page), getpagesize(), PROT_READ|PROT_EXEC))
        fail("official-step: cannot restore code permissions\n");
}
__attribute__((constructor)) void start() {
    auto* out = std::getenv("TM2020_STEP_OUT_FD");
    if (!out) return;
    out_fd = std::atoi(out);
    if (auto* in = std::getenv("TM2020_STEP_IN_FD")) in_fd = std::atoi(in);
    dl_iterate_phdr(module, nullptr);
    if (!image || out_fd < 0) fail("official-step: invalid initialization\n");
    struct sigaction act{};
    act.sa_sigaction = trap; act.sa_flags = SA_SIGINFO;
    sigemptyset(&act.sa_mask);
    if (sigaction(SIGTRAP, &act, nullptr)) fail("official-step: sigaction failed\n");
    patch(bind_off, std::array<uint8_t,7>{0x48,0x89,0x8f,0x70,0x1a,0,0});
    patch(input_off, std::array<uint8_t,5>{0xe8,0x62,0x51,0xf8,0xff});
    patch(after_off, std::array<uint8_t,11>{0x41,0xc7,0x85,0x74,0x03,0,0,0,0,0,0});
}
}

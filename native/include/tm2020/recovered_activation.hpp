#pragma once
#include "tm2020/recovered_contacts.hpp"
namespace tm2020::recovered {
struct WakeIndexState {
    std::uint32_t rest_since{};
    std::uint16_t active_index{0xffff};
    std::uint8_t reserved{},queued{};
};
static_assert(sizeof(WakeIndexState)==8);
// Original 0x7b9b70: callback-present gate, inactive index and exact byte==1
// deduplication. Queue stores the reverse-mapped HANDLE, not the body slot.
// Owns logical queue storage; native heap growth and later activation callbacks
// are separate. No later physics stage is implied by enqueue success.
bool enqueue_body_wake(bool callback_present,std::uint32_t body_slot,
    std::span<WakeIndexState> indices,std::span<const std::uint32_t> slot_to_handle,
    std::vector<std::uint32_t>& pending);
// Original 0x7fc09a..0x7fc0bd, inside its synchronization region. The caller
// must own the list; this operation alone does not implement native locking,
// wake queue consumption, callbacks, or the surrounding scene update.
bool activate_body_slot(WakeIndexState& index,std::uint32_t body_slot,
    std::span<std::uint32_t> active_slots,std::uint32_t& active_count);
// Complete leaf 0x7f4760. Raw model +0x50 word and source flag byte.
bool model_fixed_for_flags(std::uint32_t model_word_50,std::uint8_t source_flags) noexcept;
struct BodyActivationInput {
    float model_mass{1},item_mass_offset{};
    std::uint32_t model_word_50{};
    std::uint8_t source_flags{},shape_tag_11{};
    bool shape_present{};
    std::uint16_t sleep_word_4{};
};
struct BodyActivationState {
    std::uint32_t flags{}; // native item +4: only the low byte is changed
    std::uint32_t related_item_id{0xffffffff},related_state_index{0xffffffff}; // +0x28,+0x2c
    VelocityCoefficients coefficients{}; // only inverse-mass lane 3 changes
};
// Complete 0x800c00 arithmetic/control flow with typed owned inputs. Native
// pointer arrays and ID lookup are represented explicitly; no game memory is
// accessed. Mass components are finite within +/-1e6 and their sum >=1e-6.
// The tag at shape +0x11 is kept distinct from geometry's shape-type enum.
// Validates and stages the whole batch before committing; preserves all other
// flags and coefficient lanes. Later engine stages can modify these outputs.
void prepare_body_activation(std::span<BodyActivationState> states,
    std::span<const BodyActivationInput> inputs,std::span<const std::uint32_t> item_id_to_state);
}

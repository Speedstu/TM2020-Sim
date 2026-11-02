#pragma once
#include "tm2020/recovered_rigid.hpp"
namespace tm2020::recovered {
// Complete 0x7f8db0 arithmetic. The engine adds R*modelCenter (+0x40 in each
// model) before collision/solving/integration, then subtracts the NEW R*center
// afterward. This is a frame change, not a velocity or quaternion update.
// Model-origin state/force calls surround a center-frame solver phase. Reverse
// shifts retain native float rounding; they need not cancel bit-for-bit.
// Caller supplies one model center per body; entire batch is transactional.
void shift_model_center_frame(std::span<RigidState> states,
    std::span<const std::array<float,3>> model_centers,bool subtract);
}

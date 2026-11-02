#pragma once
// Calibration belongs to the user's input settings, not the executable layout.
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace tm2020::live {
inline double inverse_steering_deadzone(double desired,double deadzone) {
    if(!std::isfinite(desired)||std::abs(desired)>1||!std::isfinite(deadzone)||deadzone<0||deadzone>=.9)
        throw std::invalid_argument("Invalid steering calibration");
    if(desired==0)return 0;
    // The current-game sweep showed truncation to signed 7-bit values after
    // remapping. Half a bin centers the requested value in that quantization.
    const double magnitude=std::min(1.,std::abs(desired)+.5/127.);
    return std::copysign(deadzone+(1-deadzone)*magnitude,desired);
}
}

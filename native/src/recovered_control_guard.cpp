#include "tm2020/recovered_control_guard.hpp"
#include <cmath>
#include <stdexcept>

namespace tm2020::recovered {
namespace {
void finite(float x) {
    if (!std::isfinite(x) || std::abs(x)>10000.f)
        throw std::invalid_argument("Control guard outside finite qualified domain");
}
void validate(const NestedControlRecord& r) {
    for (float x:r.quaternion_60) finite(x);
    for (float x:r.vector_7c) finite(x);
    finite(r.fallback_f4);
}
float selected(const NestedControlRecord& r) {
    const float priority=static_cast<float>(r.priority_4e8);
    return priority!=0.f ? priority : r.fallback_f4;
}
float gate(const NestedControlRecord& r) {
    // Original 0x83dd90 conjugates the quaternion before the complete
    // 0x1955c0 transform. Retain the original operation ordering.
    const float w=r.quaternion_60[0],x=-r.quaternion_60[1];
    const float y=-r.quaternion_60[2],z=-r.quaternion_60[3];
    const float a=r.vector_7c[0],b=r.vector_7c[1],c=r.vector_7c[2];
    const float p=(c*y-b*z)+a*w;
    const float q=(a*z-x*c)+w*b;
    const float t=q*x-p*y;
    const float transformed_z=(t+t)+c;
    return selected(r)>transformed_z ? 1.f : 0.f;
}
}
float select_nested_control_value(const NestedControlRecord& r) {
    validate(r);return selected(r);
}
float nested_drive_gate(const NestedControlRecord& r) {
    validate(r);return gate(r);
}
void update_control_guard(GuardedControlScalars& state,const NestedControlRecord& r,
    float scalar) {
    validate(r);finite(state.scalar_98);finite(state.scalar_9c);finite(scalar);
    auto next=state;
    if (r.priority_4e8!=0 || r.fallback_f4!=0.f) next.scalar_98=gate(r);
    const bool clear=(r.flags_4ec&4u)!=0 || (r.flags_f0&4u)!=0;
    const bool keep=(r.flags_4ec&3u)==2 || (r.flags_f0&3u)==2;
    if (clear && !keep) next.scalar_9c=0.f;
    // vehicle +0x176c aliases nested record +0x4ec; do not model these as
    // independent flags. +0x176a is likewise nested record +0x4ea.
    if ((r.flags_4ec&0x400u)!=0) {
        const int wide=r.limit_4ea;
        const float bound=static_cast<float>(wide<0 ? -wide : wide);
        if (scalar>bound) next.scalar_98=0.f;
        if (scalar < -bound) next.scalar_9c=0.f;
    }
    state=next;
}
}

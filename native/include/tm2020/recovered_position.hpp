#pragma once
#include "tm2020/recovered_jacobian.hpp"
namespace tm2020::recovered {
// The position routines read these three floats at +0x14/+0x18/+0x1c of
// their config argument. Do not reinterpret SolverParameters as this object.
enum class PositionMathPath : std::uint32_t { scalar_sse2=0, fused_avx_fma=1 };
struct PositionParameters {float allowed_separation{},maximum_correction{},factor{};};
// Ports of 0x85e4f0 / 0x85e7d0, including the selected scalar SSE2 or AVX/FMA path's exact
// small-angle sine/cosine polynomials. Angular correction norm is restricted
// to <=1.57079625 radians; larger corrections are rejected transactionally.
// This domain avoids unported larger-angle argument reduction. The FMA path
// uses explicit std::fma so the port does not require AVX instructions.
void correct_rotation(RigidState& state,const std::array<float,3>& correction,bool negative=false,PositionMathPath math=PositionMathPath::scalar_sse2);
// One complete sweep of 0x8603b0 / 0x860980 arithmetic, within the rotation
// domain above. Caller chooses iteration count/order and native config values.
void solve_dynamic_positions(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,
    std::span<const DynamicPositionConstraint> constraints,const PositionParameters& parameters,PositionMathPath math=PositionMathPath::scalar_sse2);
void solve_static_positions(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,
    std::span<const StaticPositionConstraint> constraints,const PositionParameters& parameters,PositionMathPath math=PositionMathPath::scalar_sse2);
}

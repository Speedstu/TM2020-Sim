#include "tm2020/recovered_features.hpp"
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
// Port of complete SHA-pinned 0x1c9080. Register/branch temporaries retain the
// decompiler's numbering to make the original piecewise control flow auditable.
// All arithmetic is independently qualified against original x64 instructions.
float edge_pair_raw
                (const float *param_1,const float *param_2,float param_3,const float *param_4,const float *param_5,
                float param_6,float *param_7,float *param_8)

{
  float fVar1;
  float fVar2;
  float fVar3;
  float fVar4;
  float fVar5;
  float fVar6;
  float fVar7;
  float fVar8;
  float fVar9;
  float fVar10;
  float fVar11;
  float fVar12;
  
  fVar6 = param_1[2] - param_4[2];
  fVar7 = *param_1 - *param_4;
  fVar12 = param_1[1] - param_4[1];
  fVar10 = param_2[1] * fVar12 + *param_2 * fVar7 + param_2[2] * fVar6;
  fVar9 = (-((*param_5 * *param_2 + param_5[1] * param_2[1] + param_5[2] * param_2[2])));
  fVar11 = (-((param_5[1] * fVar12 + *param_5 * fVar7 + param_5[2] * fVar6)));
  fVar8 = std::abs((1.f - fVar9 * fVar9));
  if (fVar8 < 9.999999747378752e-6f) {
    param_3 = param_3 + param_6;
    fVar8 = 1.f;
    if (0.0 < fVar9) {
      fVar8 = (-1.f);
    }
    fVar9 = (fVar10 - fVar8 * fVar11) * .5f;
    fVar10 = (-(fVar9));
    fVar4 = (-(param_3));
    if (((-(param_3)) <= fVar10) && (fVar4 = param_3, fVar10 <= param_3))
    {
      fVar4 = fVar10;
    }
    fVar3 = ((-(fVar8)) * fVar4 * param_6) / param_3;
    fVar11 = (fVar9 + fVar9 + fVar4) * fVar4;
    fVar4 = fVar8 * fVar3 + fVar4;
    goto LAB_1401c974c;
  }
  fVar1 = fVar8 * param_6;
  fVar4 = fVar11 * fVar9 - fVar10;
  fVar5 = (-(fVar1));
  fVar2 = fVar10 * fVar9 - fVar11;
  fVar3 = param_6;
  if (fVar4 < (-((fVar8 * param_3)))) {
    if (fVar2 < fVar5) {
      fVar3 = (-(param_6));
      fVar4 = (-((fVar3 * fVar9 + fVar10)));
      if (param_3 < fVar4) {
        fVar11 = (param_3 - (fVar4 + fVar4)) * param_3 + (fVar11 + fVar11 + fVar3) * fVar3;
        fVar4 = param_3;
        goto LAB_1401c974c;
      }
      if ((-(param_3)) <= fVar4) {
        fVar11 = (fVar11 + fVar11 + fVar3) * fVar3 - fVar4 * fVar4;
        goto LAB_1401c974c;
      }
    }
    else if (fVar1 < fVar2) {
      fVar4 = (-((fVar9 * param_6 + fVar10)));
      if (param_3 < fVar4) {
        fVar11 = (param_3 - (fVar4 + fVar4)) * param_3 + (fVar11 + fVar11 + param_6) * param_6;
        fVar4 = param_3;
        goto LAB_1401c974c;
      }
      if ((-(param_3)) <= fVar4) {
        fVar11 = (fVar11 + fVar11 + param_6) * param_6 - fVar4 * fVar4;
        goto LAB_1401c974c;
      }
    }
    fVar4 = (-(param_3));
    fVar8 = (-(param_6));
    fVar3 = (-((fVar4 * fVar9 + fVar11)));
    fVar11 = (fVar10 + fVar10 + fVar4) * fVar4;
    if (fVar8 <= fVar3) {
      if (param_6 < fVar3) {
        fVar11 = (param_6 - (fVar3 + fVar3)) * param_6 + fVar11;
        fVar3 = param_6;
      }
      else {
        fVar11 = fVar11 - fVar3 * fVar3;
      }
    }
    else {
      fVar11 = (fVar8 - (fVar3 + fVar3)) * fVar8 + fVar11;
      fVar3 = fVar8;
    }
    goto LAB_1401c974c;
  }
  if (fVar4 <= fVar8 * param_3) {
    fVar11 = fVar11 + fVar11;
    if (fVar2 < fVar5) {
      fVar3 = (-(param_6));
      fVar8 = (-(param_3));
      fVar11 = (fVar3 + fVar11) * fVar3;
      fVar4 = (-((fVar3 * fVar9 + fVar10)));
      if (fVar8 <= fVar4) {
        if (param_3 < fVar4) {
          fVar11 = (param_3 - (fVar4 + fVar4)) * param_3 + fVar11;
          fVar4 = param_3;
        }
        else {
          fVar11 = fVar11 - fVar4 * fVar4;
        }
      }
      else {
        fVar11 = (fVar8 - (fVar4 + fVar4)) * fVar8 + fVar11;
        fVar4 = fVar8;
      }
    }
    else if (fVar1 < fVar2) {
      fVar8 = (-(param_3));
      fVar11 = (fVar11 + param_6) * param_6;
      fVar4 = (-((fVar9 * param_6 + fVar10)));
      if (fVar8 <= fVar4) {
        if (param_3 < fVar4) {
          fVar11 = (param_3 - (fVar4 + fVar4)) * param_3 + fVar11;
          fVar4 = param_3;
        }
        else {
          fVar11 = fVar11 - fVar4 * fVar4;
        }
      }
      else {
        fVar11 = (fVar8 - (fVar4 + fVar4)) * fVar8 + fVar11;
        fVar4 = fVar8;
      }
    }
    else {
      fVar4 = fVar4 * (1.f / fVar8);
      fVar3 = fVar2 * (1.f / fVar8);
      fVar11 = (fVar3 * fVar9 + fVar4 + fVar10 + fVar10) * fVar4 +
               (fVar4 * fVar9 + fVar3 + fVar11) * fVar3;
    }
    goto LAB_1401c974c;
  }
  if (fVar2 < fVar5) {
    fVar4 = (-(param_3));
    fVar3 = (-(param_6));
    fVar8 = (-((fVar3 * fVar9 + fVar10)));
    if (fVar8 < fVar4) {
      fVar11 = (fVar4 - (fVar8 + fVar8)) * fVar4 + (fVar11 + fVar11 + fVar3) * fVar3;
      goto LAB_1401c974c;
    }
    if (fVar8 <= param_3) {
      fVar11 = (fVar11 + fVar11 + fVar3) * fVar3 - fVar8 * fVar8;
      fVar4 = fVar8;
      goto LAB_1401c974c;
    }
    fVar8 = (-((fVar9 * param_3 + fVar11)));
    fVar11 = (fVar10 + fVar10 + param_3) * param_3;
    if (param_6 < fVar8) goto LAB_1401c9502;
    if (fVar8 < fVar3) goto LAB_1401c944f;
  }
  else {
    if (fVar1 < fVar2) {
      fVar4 = (-(param_3));
      fVar8 = (-((fVar9 * param_6 + fVar10)));
      if (fVar8 < fVar4) {
        fVar11 = (fVar4 - (fVar8 + fVar8)) * fVar4 + (fVar11 + fVar11 + param_6) * param_6;
        goto LAB_1401c974c;
      }
      if (fVar8 <= param_3) {
        fVar11 = (fVar11 + fVar11 + param_6) * param_6 - fVar8 * fVar8;
        fVar4 = fVar8;
        goto LAB_1401c974c;
      }
      fVar8 = (-((fVar9 * param_3 + fVar11)));
      fVar11 = (fVar10 + fVar10 + param_3) * param_3;
      if (fVar8 < (-(param_6))) goto LAB_1401c944f;
    }
    else {
      fVar8 = (-((fVar9 * param_3 + fVar11)));
      fVar11 = (fVar10 + fVar10 + param_3) * param_3;
      if (fVar8 < (-(param_6))) {
LAB_1401c944f:
        fVar3 = (-(param_6));
        fVar11 = (fVar3 - (fVar8 + fVar8)) * fVar3 + fVar11;
        fVar4 = param_3;
        goto LAB_1401c974c;
      }
    }
    if (param_6 < fVar8) {
LAB_1401c9502:
      fVar11 = (param_6 - (fVar8 + fVar8)) * param_6 + fVar11;
      fVar3 = param_6;
      fVar4 = param_3;
      goto LAB_1401c974c;
    }
  }
  fVar11 = fVar11 - fVar8 * fVar8;
  fVar3 = fVar8;
  fVar4 = param_3;
LAB_1401c974c:
  fVar11 = fVar12 * fVar12 + fVar7 * fVar7 + fVar6 * fVar6 + fVar11;
  if (param_7 != (float *)0x0) {
    *param_7 = fVar4;
  }
  if (param_8 != (float *)0x0) {
    *param_8 = fVar3;
  }
  fVar6 = 0.0;
  if (0.0 <= fVar11) {
    fVar6 = fVar11;
  }
  return fVar6;
}


void valid_edge(const EdgeFrame& edge){
    for(const auto* v:{&edge.center,&edge.direction})for(float x:*v)if(!std::isfinite(x)||std::abs(x)>1e6f)throw std::invalid_argument("Edge pair exceeds finite domain");
    const auto& d=edge.direction;const float squared=(d[0]*d[0]+d[1]*d[1])+d[2]*d[2];
    if(std::abs(squared-1.f)>2e-4f||!std::isfinite(edge.half_length)||edge.half_length<0||edge.half_length>1e6f)throw std::invalid_argument("Edge pair requires unit directions and nonnegative half lengths");
}
}
EdgePairResult closest_edges(const EdgeFrame& a,const EdgeFrame& b){
    valid_edge(a);valid_edge(b);if(!(a.half_length+b.half_length>0))throw std::invalid_argument("Degenerate edge pair outside finite parallel domain");
    EdgePairResult out{};out.squared_distance=edge_pair_raw(a.center.data(),a.direction.data(),a.half_length,b.center.data(),b.direction.data(),b.half_length,&out.parameter_a,&out.parameter_b);
    for(float x:{out.squared_distance,out.parameter_a,out.parameter_b})if(!std::isfinite(x))throw std::invalid_argument("Edge pair output is nonfinite");
    return out;
}
}

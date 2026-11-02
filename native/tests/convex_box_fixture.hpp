#pragma once
#include "tm2020/recovered_convex_collision.hpp"
namespace tm2020::testing {
struct BoxGeometry {
    std::array<recovered::ConvexVector,8> vertices{};
    const std::array<recovered::ConvexVector,3> axes{{{1,0,0},{0,1,0},{0,0,1}}};
    const std::array<std::array<std::uint32_t,4>,6> indices{{{0,4,6,2},{1,3,7,5},{0,1,5,4},{2,6,7,3},{0,2,3,1},{4,5,7,6}}};
    std::array<recovered::ConvexFace,6> faces{};
    const std::array<recovered::ConvexEdge,12> edges{{{0,1,0},{2,3,0},{4,5,0},{6,7,0},{0,2,1},{1,3,1},{4,6,1},{5,7,1},{0,4,2},{1,5,2},{2,6,2},{3,7,2}}};
    explicit BoxGeometry(const recovered::ConvexVector& half){
        for(std::size_t i=0;i<8;i++)for(std::size_t k=0;k<3;k++)vertices[i][k]=(i&(1u<<k))?half[k]:-half[k];
        for(std::size_t i=0;i<6;i++)faces[i]={std::uint32_t(i/2),i%2!=0,indices[i]};
    }
    BoxGeometry(const BoxGeometry&)=delete;
    recovered::ConvexTopologyView view()const{return {{vertices,axes,axes},faces,edges};}
};
}

#include "tm2020/recovered_raycast.hpp"
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::recovered;
void require(bool value){if(!value)throw std::runtime_error("Original ray boundary contract changed");}
int main()try{
    const std::array<std::array<float,3>,3> points{{{0,0,0},{0,0,4},{4,0,0}}};
    const CookedTriangle triangle{{0,1,0},0,{0,1,2},0,0};
    RayTriangleHit hit{1,42,99};
    require(raycast_cooked_triangle(points,triangle,{1,1,1},{0,-2,0},false,hit));
    require(hit.fraction==.5f&&hit.u==.25f&&hit.v==.25f);
    hit={1,42,99};const auto initial=hit;
    require(!raycast_cooked_triangle(points,triangle,{1,-1,1},{0,2,0},false,hit));
    require(std::memcmp(&hit,&initial,sizeof(hit))==0);
    require(raycast_cooked_triangle(points,triangle,{1,-1,1},{0,2,0},true,hit)&&hit.fraction==.5f);
    hit=initial;
    // Endpoint +0 has the same sign as the initial positive plane distance.
    require(!raycast_cooked_triangle(points,triangle,{1,1,1},{0,-1,0},true,hit));
    require(std::memcmp(&hit,&initial,sizeof(hit))==0);
    require(raycast_cooked_triangle(points,triangle,{1,-1,1},{0,1,0},true,hit)&&hit.fraction==1);
    hit=initial;
    try{raycast_cooked_triangle(points,triangle,{1,1,1},{0,std::numeric_limits<float>::infinity(),0},true,hit);require(false);}
    catch(const std::invalid_argument&){}
    require(std::memcmp(&hit,&initial,sizeof(hit))==0);
    auto invalid=triangle;invalid.vertices[2]=3;
    try{raycast_cooked_triangle(points,invalid,{1,1,1},{0,-2,0},true,hit);require(false);}
    catch(const std::invalid_argument&){}
    require(std::memcmp(&hit,&initial,sizeof(hit))==0);
    std::cout<<"PASS RAY_BOUNDARIES original_two_sided_endpoint_semantics=true no_partial_output_on_miss=true\n";
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}

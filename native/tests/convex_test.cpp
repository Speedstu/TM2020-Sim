#include "tm2020/recovered_convex.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool value,const char* why){if(!value)throw std::runtime_error(why);}
int main()try{
    const std::array<ConvexVector,8> a{{{-1,-1,-1},{-1,-1,1},{-1,1,-1},{-1,1,1},{1,-1,-1},{1,-1,1},{1,1,-1},{1,1,1}}};
    const std::array<ConvexVector,3> axes{{{1,0,0},{0,1,0},{0,0,1}}};auto b=a;
    for(auto& p:b)p[0]+=3;
    const ConvexAxesView av{a,axes,axes},bv{b,axes,axes};
    const auto projection=project_vertices(a,{1,0,0});check(projection.minimum==-1&&projection.maximum==1,"Cube projection wrong");
    check(!separating_axes(av,bv).overlap,"Separated cubes admitted");
    for(auto& p:b)p[0]-=1;
    const auto touching=separating_axes(av,bv);check(touching.overlap&&touching.has_witness&&touching.depth==0&&touching.normal[0]==-1,"Closed convex tangency wrong");
    for(auto& p:b)p[0]-=.5f;
    const auto impact=separating_axes(av,bv);check(impact.overlap&&impact.depth==.5f&&impact.kind==0&&impact.index_a==0,"Convex penetration witness wrong");
    for(auto& p:b)p[0]+=.7f;
    check(!separating_axes(av,bv).overlap&&separating_axes(av,bv,.25f).overlap,"SAT margin expansion wrong");
    const auto missing=separating_axes({a,{},{}},{b,{},{}},0);
    check(missing.overlap&&!missing.has_witness&&missing.depth==std::numeric_limits<float>::max(),"Missing-axis native sentinel changed");
    bool denied=false;try{project_vertices({},{});}catch(const std::invalid_argument&){denied=true;}check(denied,"Empty projection not rejected");
    denied=false;try{separating_axes(av,bv,-1);}catch(const std::invalid_argument&){denied=true;}check(denied,"Negative margin not rejected");
    std::cout<<"PASS CONVEX_SAT separation=true tangency=true margin=true witness=true missing_axis_contract=true complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

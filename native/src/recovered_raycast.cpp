#include "tm2020/recovered_raycast.hpp"
#include <bit>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
bool safe_div(float a,float b,float& result){
    const auto absolute=std::abs(b);
    if(1.f>absolute&&!(std::abs(a)<absolute*3.4028233e32f))return false;
    result=a/b;return true;
}
bool bary(float e1a,float e2a,float pa,float e1b,float e2b,float pb,float& u,float& v){
    const float determinant=e1a*e2b-e2a*e1b;
    const float numerator_u=pa*e2b-e2a*pb,numerator_v=e1a*pb-pa*e1b;
    const float limit=std::abs(determinant)*100000.f;
    if(!(limit>std::abs(numerator_u))||!(limit>std::abs(numerator_v)))return false;
    const float inverse=1.f/determinant;u=inverse*numerator_u;v=inverse*numerator_v;return true;
}
}
bool raycast_sphere(const std::array<float,3>& center,float radius,std::uint16_t material,
    const std::array<float,3>& origin,const std::array<float,3>& direction,
    const std::array<float,3>& displacement,std::uint8_t skip,RaySphereHit& hit){
    auto valid=[](float v){if(!std::isfinite(v)||std::abs(v)>1e6f)throw std::invalid_argument("Ray-sphere finite input domain");};
    for(auto v:center)valid(v);
    for(auto v:origin)valid(v);
    for(auto v:direction)valid(v);
    for(auto v:displacement)valid(v);
    valid(radius);valid(hit.fraction);if(radius<0)throw std::invalid_argument("Negative sphere radius");
    if(std::uint8_t(material)==skip)return false;
    std::array<float,3> delta{},relative{};
    for(unsigned k=0;k<3;k++){delta[k]=origin[k]-center[k];relative[k]=direction[k]-displacement[k];}
    const float c=((delta[1]*delta[1]+delta[0]*delta[0])+delta[2]*delta[2])-radius*radius;
    float fraction=0.f;
    if(c>0.f){
        const float a=(relative[1]*relative[1]+relative[0]*relative[0])+relative[2]*relative[2];
        const float dot=(relative[1]*delta[1]+relative[0]*delta[0])+relative[2]*delta[2];
        const float b=dot+dot;
        if(std::abs(a)<.00001f){
            if(std::abs(b)<.00001f){if(!(std::abs(c)<.00001f))return false;}
            else fraction=-c/b;
        }else{
            const float discriminant=b*b-(a*4.f)*c;
            if(discriminant<0.f)return false;
            const float root=std::sqrt(discriminant),scale=.5f/a;
            fraction=scale*(-b-root);
        }
        if(fraction<0.f||fraction>1.f)return false;
    }
    if(!(hit.fraction>fraction))return false;
    RaySphereHit next{};next.fraction=fraction;next.material=material;
    for(unsigned k=0;k<3;k++){
        next.point[k]=origin[k]+direction[k]*fraction;
        next.normal[k]=next.point[k]-(center[k]+displacement[k]*fraction);
    }
    const auto& n=next.normal;
    const float squared=(n[1]*n[1]+n[0]*n[0])+n[2]*n[2];
    if(squared>1e-10f&&squared<std::numeric_limits<float>::max()){
        const float inverse=1.f/std::sqrt(squared);for(auto& v:next.normal)v*=inverse;
    }
    hit=next;return true;
}
bool raycast_cooked_triangle(const std::array<std::array<float,3>,3>& vertices,
    const CookedTriangle& triangle,const std::array<float,3>& origin,
    const std::array<float,3>& direction,bool two_sided,RayTriangleHit& hit){
    auto valid=[](float value){if(!std::isfinite(value)||std::abs(value)>1e6f)throw std::invalid_argument("Ray-triangle finite input domain");};
    for(const auto& row:vertices)for(auto value:row)valid(value);
    for(auto value:origin)valid(value);
    for(auto value:direction)valid(value);
    for(auto value:triangle.normal)valid(value);
    valid(triangle.plane_constant);
    valid(hit.fraction);valid(hit.u);valid(hit.v);
    for(auto index:triangle.vertices)if(index>=3)throw std::invalid_argument("Ray-triangle vertex index");
    const auto& n=triangle.normal;
    const float plane=((n[1]*origin[1]+n[0]*origin[0])+n[2]*origin[2])+triangle.plane_constant;
    float fraction{};
    if(two_sided){
        const float end=((origin[0]+direction[0])*n[0]+(origin[1]+direction[1])*n[1])
            +(origin[2]+direction[2])*n[2]+triangle.plane_constant;
        if(((std::bit_cast<std::uint32_t>(end)^std::bit_cast<std::uint32_t>(plane))&0x80000000u)==0)return false;
        if(!safe_div(plane,end-plane,fraction))return false;
        fraction=std::abs(fraction);
    }else{
        if(0.f>plane)return false;
        const float approach=-((n[0]*direction[0]+n[1]*direction[1])+n[2]*direction[2]);
        if(plane>approach||!safe_div(plane,approach,fraction))return false;
    }
    if(fraction>hit.fraction)return false;
    const auto& a=vertices[triangle.vertices[0]];
    const auto& b=vertices[triangle.vertices[1]];
    const auto& c=vertices[triangle.vertices[2]];
    std::array<float,3> projected{},e1{},e2{};
    for(std::size_t i=0;i<3;i++){projected[i]=(direction[i]*fraction+origin[i])-a[i];e1[i]=b[i]-a[i];e2[i]=c[i]-a[i];}
    unsigned axis=std::abs(n[1])>std::abs(n[0])?1:0;
    if(std::abs(n[2])>std::abs(n[axis]))axis=2;
    const auto first=(axis+1)%3,second=(axis+2)%3;
    float u{},v{};
    if(!bary(e1[first],e2[first],projected[first],e1[second],e2[second],projected[second],u,v)
        ||!(u>=0.f)||!(v>=0.f)||!(1.f>=u+v))return false;
    hit={fraction,u,v};return true;
}
}

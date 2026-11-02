#include "tm2020/recovered_position.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
template<std::size_t N>void bounded(const std::array<float,N>& a){for(float x:a)require(std::isfinite(x)&&std::abs(x)<=1e6f,"Position input/output exceeds finite domain");}
double constant(std::uint64_t bits){return std::bit_cast<double>(bits);}
float native_small_cos(float value){
    const double x=value,z=x*x,z2=z*z;
    double a=constant(0xbe927e4fb7789f5c)*z;
    double b=constant(0xbf56c16c16c16c16)*z;
    double c=constant(0xbfe0000000000000)*z;
    a=a+constant(0x3efa01a01a01a019);a=a*z2;
    b=b+constant(0x3fa5555555555555);a=a+b;a=a*z2;
    c=c+1.;return static_cast<float>(c+a);
}
float native_small_sin(float value){
    const double x=value;const double abs=std::abs(x);
    if(abs<constant(0x3f20000000000000))return value;
    if(abs<constant(0x3f80000000000000)){
        double t=x*x;t=t*x;t=t*constant(0x3fc5555555555555);return static_cast<float>(x-t);
    }
    const double z=x*x,z2=z*z;
    double a=constant(0x3ec71de3a556c734)*z;
    double b=constant(0x3f81111111111111)*z;
    const double c=x*z;
    a=a+constant(0xbf2a01a01a01a01a);a=a*z2;
    b=b+constant(0xbfc5555555555555);a=a+b;a=a*c;
    return static_cast<float>(x+a);
}
float native_fused_cos(float value){
 const double x=value,abs=std::abs(x);if(abs<0.0001220703125)return 1;
 if(abs<0.0078125)return static_cast<float>(std::fma(-(x*.5),x,1.));
 const double z=x*x,z2=z*z,base=1.-z*.5;
 double p=std::fma(z,constant(0xbe927e4fb7789f5c),constant(0x3efa01a01a01a019));
 p=std::fma(p,z,constant(0xbf56c16c16c16c16));p=std::fma(p,z,constant(0x3fa5555555555555));return static_cast<float>(std::fma(p,z2,base));
}
float native_fused_sin(float value){
 const double x=value,abs=std::abs(x);if(abs<0.0001220703125)return value;
 const double z=x*x;if(abs<0.0078125)return static_cast<float>(std::fma(-(z*x),constant(0x3fc5555555555555),x));
 double p=std::fma(z,constant(0x3ec71de3a556c734),constant(0xbf2a01a01a01a01a));p=std::fma(p,z,constant(0x3f81111111111111));p=std::fma(p,z,constant(0xbfc5555555555555));return static_cast<float>(std::fma(p,x*z,x));
}
std::array<float,3> cross(const std::array<float,3>& a,const std::array<float,3>& b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
float dot(const std::array<float,3>& a,const std::array<float,3>& b){return (a[1]*b[1]+a[0]*b[0])+a[2]*b[2];}
std::array<float,3> sub(const std::array<float,3>& a,const std::array<float,3>& b){return {a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
std::array<float,3> world(const RigidState& s,const std::array<float,3>& p){
    std::array<float,3> out{};for(std::size_t k=0;k<3;k++)out[k]=((p[1]*s.rotation[k*3+1]+p[0]*s.rotation[k*3])+p[2]*s.rotation[k*3+2])+s.position[k];return out;
}
std::array<float,3> weighted(const std::array<float,3>& a,const VelocityCoefficients& c){return {a[0]*c[0],a[1]*c[1],a[2]*c[2]};}
void valid_states(std::span<const RigidState> s){for(const auto& b:s){bounded(b.position);bounded(b.rotation);bounded(b.quaternion);}}
void inputs(std::span<const RigidState> s,std::span<const VelocityCoefficients> c,const PositionParameters& p,std::size_t count){
    require(s.size()==c.size()&&s.size()<=1000000&&count<=1000000,"Position buffer count invalid");valid_states(s);
    for(const auto& v:c){bounded(v);for(float x:v)require(x>=0,"Negative position velocity coefficient");}
    bounded(std::array{p.allowed_separation,p.maximum_correction,p.factor});require(p.maximum_correction>=0&&p.factor>=0,"Invalid position solver parameters");
}
float gap(const std::array<float,3>& a,const std::array<float,3>& b,const std::array<float,3>& n,const PositionParameters& p){
    const float g=dot(sub(b,a),n)+p.allowed_separation;const float lo=-p.maximum_correction;
    return g>lo?g:lo; // MAXSS returns second operand on equality.
}
float scale(float denom,float error,const PositionParameters& p){require(denom>0&&std::isfinite(denom),"Singular position constraint");return ((-1.f)/denom)*p.factor*error;}
}
void correct_rotation(RigidState& state,const std::array<float,3>& correction,bool negative,PositionMathPath math){
    require(math==PositionMathPath::scalar_sse2||math==PositionMathPath::fused_avx_fma,"Unknown position math path");
    bounded(correction);bounded(state.quaternion);bounded(state.rotation);
    const float squared=(correction[0]*correction[0]+correction[1]*correction[1])+correction[2]*correction[2];
    const float norm=std::sqrt(squared);require(norm<=1.57079625f,"Angular position correction exceeds recovered trig domain");
    if(norm<=std::bit_cast<float>(std::uint32_t{0x358637bd}))return;
    const float inverse=1.f/norm;const float angle=negative?-norm:norm;const float half=.5f*angle;
    const float cosine=math==PositionMathPath::fused_avx_fma?native_fused_cos(half):native_small_cos(half),sine=math==PositionMathPath::fused_avx_fma?native_fused_sin(half):native_small_sin(half);
    const std::array d{cosine,(correction[0]*inverse)*sine,(correction[1]*inverse)*sine,(correction[2]*inverse)*sine};
    const auto q=state.quaternion;
    std::array<float,4> out{
        q[0]*d[0]-((d[2]*q[2]+q[1]*d[1])+d[3]*q[3]),
        ((q[1]*d[0]+q[0]*d[1])+q[3]*d[2])-q[2]*d[3],
        ((q[2]*d[0]+q[0]*d[2])+q[1]*d[3])-q[3]*d[1],
        ((q[3]*d[0]+q[0]*d[3])+q[2]*d[1])-q[1]*d[2]};
    const float length=std::sqrt(((out[0]*out[0]+out[1]*out[1])+out[2]*out[2])+out[3]*out[3]);
    const float normalization=1.f/length;
    if(normalization>pose_remainder_cutoff&&normalization<std::numeric_limits<float>::max())for(float& x:out)x=x*normalization;
    else out={1,0,0,0};
    auto next=state;next.quaternion=out;quaternion_to_matrix(next.rotation,out);bounded(next.rotation);bounded(next.quaternion);state=next;
}
void solve_static_positions(std::span<RigidState> states,std::span<const VelocityCoefficients> c,
    std::span<const StaticPositionConstraint> constraints,const PositionParameters& parameters,PositionMathPath math){
    require(math==PositionMathPath::scalar_sse2||math==PositionMathPath::fused_avx_fma,"Unknown position math path");
    inputs(states,c,parameters,constraints.size());for(const auto& x:constraints){require(x.body<states.size(),"Static position body out of range");bounded(x.local_point);bounded(x.target_point);bounded(x.normal);}
    auto next=std::vector<RigidState>(states.begin(),states.end());
    for(const auto& x:constraints){
        auto& s=next[x.body];const auto a=world(s,x.local_point);const float error=gap(a,x.target_point,x.normal,parameters);if(error>=0)continue;
        std::array<float,3> r{};for(std::size_t k=0;k<3;k++)r[k]=(a[k]+x.target_point[k])*.5f-s.position[k];
        const auto angular=cross(r,x.normal),w=weighted(angular,c[x.body]);const float impulse=scale(dot(w,angular)+c[x.body][3],error,parameters);
        const float linear=impulse*c[x.body][3];std::array<float,3> rotation{};
        for(std::size_t k=0;k<3;k++){s.position[k]=s.position[k]-x.normal[k]*linear;rotation[k]=w[k]*impulse;}
        correct_rotation(s,rotation,true,math);
    }
    valid_states(next);std::copy(next.begin(),next.end(),states.begin());
}
void solve_dynamic_positions(std::span<RigidState> states,std::span<const VelocityCoefficients> c,
    std::span<const DynamicPositionConstraint> constraints,const PositionParameters& parameters,PositionMathPath math){
    require(math==PositionMathPath::scalar_sse2||math==PositionMathPath::fused_avx_fma,"Unknown position math path");
    inputs(states,c,parameters,constraints.size());for(const auto& x:constraints){require(x.body_a<states.size()&&x.body_b<states.size(),"Dynamic position body out of range");bounded(x.local_a);bounded(x.local_b);bounded(x.normal);}
    auto next=std::vector<RigidState>(states.begin(),states.end());
    for(const auto& x:constraints){
        auto& a=next[x.body_a];auto& b=next[x.body_b];const auto pa=world(a,x.local_a),pb=world(b,x.local_b);
        const float error=gap(pa,pb,x.normal,parameters);if(error>=0)continue;
        std::array<float,3> ra{},rb{};for(std::size_t k=0;k<3;k++){const float midpoint=(pb[k]+pa[k])*.5f;ra[k]=midpoint-a.position[k];rb[k]=midpoint-b.position[k];}
        const auto aa=cross(ra,x.normal),ab=cross(rb,x.normal),wa=weighted(aa,c[x.body_a]),wb=weighted(ab,c[x.body_b]);
        const float denominator=(dot(wa,aa)+c[x.body_a][3])+(dot(wb,ab)+c[x.body_b][3]);const float impulse=scale(denominator,error,parameters);
        const float linear_a=impulse*c[x.body_a][3],linear_b=impulse*c[x.body_b][3];std::array<float,3> rotate_a{},rotate_b{};
        for(std::size_t k=0;k<3;k++){a.position[k]=a.position[k]-x.normal[k]*linear_a;rotate_a[k]=wa[k]*impulse;rotate_b[k]=wb[k]*impulse;}
        correct_rotation(a,rotate_a,true,math);
        for(std::size_t k=0;k<3;k++)b.position[k]=x.normal[k]*linear_b+b.position[k];
        correct_rotation(b,rotate_b,false,math);
    }
    valid_states(next);std::copy(next.begin(),next.end(),states.begin());
}
}

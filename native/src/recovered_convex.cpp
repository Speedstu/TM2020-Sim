#include "tm2020/recovered_convex.hpp"
#include <bit>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
void bounded(const ConvexVector& v){for(float x:v)require(std::isfinite(x)&&std::abs(x)<=1e6f,"Convex vector exceeds finite domain");}
float dot(const ConvexVector& a,const ConvexVector& b){return (a[1]*b[1]+a[0]*b[0])+a[2]*b[2];}
ConvexVector cross(const ConvexVector& a,const ConvexVector& b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
ProjectionInterval project(std::span<const ConvexVector> v,const ConvexVector& axis){
    const float first=dot(axis,v[0]);ProjectionInterval out{first,first};
    for(std::size_t i=1;i<v.size();i++){
        const float x=dot(axis,v[i]);out.minimum=x<out.minimum?x:out.minimum;out.maximum=x>out.maximum?x:out.maximum;
    }
    return out;
}
void validate(const ConvexAxesView& v){
    require(!v.vertices.empty()&&v.vertices.size()<=1000000&&v.face_normals.size()<=256&&v.edge_directions.size()<=256,"Convex buffer count invalid");
    for(const auto& p:v.vertices)bounded(p);
    for(const auto& n:v.face_normals)bounded(n);
    for(const auto& e:v.edge_directions)bounded(e);
}
bool axis_test(const ConvexAxesView& a,const ConvexAxesView& b,float margin,const ConvexVector& axis,
    std::uint8_t kind,std::uint8_t index_a,std::uint8_t index_b,float bias,SeparatingAxisResult& out){
    const auto pa=project(a.vertices,axis),pb=project(b.vertices,axis);
    const float high=pa.maximum+margin,low=pa.minimum-margin;
    if(pb.minimum>high||low>pb.maximum)return false;
    const float positive=high-pb.minimum,negative=pb.maximum-low;
    const float depth=positive<negative?positive:negative; // MINSS tie -> second.
    if(out.depth>depth+bias){
        out.depth=depth;out.has_witness=true;out.kind=kind;out.index_a=index_a;out.index_b=kind==2?index_b:0;
        if(negative>positive)for(std::size_t k=0;k<3;k++)out.normal[k]=-axis[k];else out.normal=axis;
    }
    return true;
}
}
ProjectionInterval project_vertices(std::span<const ConvexVector> vertices,const ConvexVector& axis){
    require(!vertices.empty()&&vertices.size()<=1000000,"Projection requires bounded nonempty vertices");bounded(axis);for(const auto& v:vertices)bounded(v);return project(vertices,axis);
}
SeparatingAxisResult separating_axes(const ConvexAxesView& a,const ConvexAxesView& b,float margin){
    validate(a);validate(b);require(std::isfinite(margin)&&margin>=0&&margin<=1e6f,"Invalid SAT margin");
    const auto axes=a.face_normals.size()+b.face_normals.size()+a.edge_directions.size()*b.edge_directions.size();
    require(axes*(a.vertices.size()+b.vertices.size())<=100000000,"SAT work exceeds bounded kernel domain");
    SeparatingAxisResult out{};out.depth=std::numeric_limits<float>::max();
    for(std::size_t i=0;i<a.face_normals.size();i++)if(!axis_test(a,b,margin,a.face_normals[i],0,std::uint8_t(i),0,0,out))return out;
    for(std::size_t i=0;i<b.face_normals.size();i++)if(!axis_test(a,b,margin,b.face_normals[i],1,std::uint8_t(i),0,0,out))return out;
    for(std::size_t i=0;i<a.edge_directions.size();i++)for(std::size_t j=0;j<b.edge_directions.size();j++){
        auto normal=cross(a.edge_directions[i],b.edge_directions[j]);const float squared=dot(normal,normal);
        if(squared<=std::bit_cast<float>(std::uint32_t{0x2edbe6ff})||squared>=std::numeric_limits<float>::max())continue;
        const float inverse=1.f/std::sqrt(squared);for(float& x:normal)x=x*inverse;
        if(!axis_test(a,b,margin,normal,2,std::uint8_t(i),std::uint8_t(j),9.999999747378752e-5f,out))return out;
    }
    out.overlap=true;return out;
}
}

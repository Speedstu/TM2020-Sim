#include "tm2020/recovered_mesh.hpp"
#include <bit>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
using Vec=std::array<float,3>;
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
template<std::size_t N>void bounded(const std::array<float,N>& v){for(float x:v)require(std::isfinite(x)&&std::abs(x)<=1e6f,"Mesh kernel input/output exceeds finite domain");}
float dot(const Vec& a,const Vec& b){return (a[1]*b[1]+a[0]*b[0])+a[2]*b[2];}
Vec sub(const Vec& a,const Vec& b){return {a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
Vec cross(const Vec& a,const Vec& b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
Vec rotate(const MeshTransform& transform,const Vec& p){
    Vec out{};for(std::size_t k=0;k<3;k++)out[k]=(p[1]*transform.rotation[3*k+1]+p[0]*transform.rotation[3*k])+p[2]*transform.rotation[3*k+2];return out;
}
Vec world(const MeshTransform& transform,const Vec& p){auto out=rotate(transform,p);for(std::size_t k=0;k<3;k++)out[k]=out[k]+transform.translation[k];return out;}
float minimum(float a,float b){return a<b?a:b;} // SSE MINSS tie -> second input
float maximum(float a,float b){return a>b?a:b;}
void validate_tree(std::span<const AabbNode> nodes){
    require(nodes.size()<=2000000,"Too many AABB nodes");
    for(std::size_t i=0;i<nodes.size();i++){
        const auto& n=nodes[i];bounded(n.center);bounded(n.half_extent);for(float x:n.half_extent)require(x>=0,"Negative AABB half extent");
        if(!(n.packed&1)){const auto skip=n.packed>>1;require(skip>0&&skip<=nodes.size()-i,"Invalid AABB subtree skip");}
    }
}
std::vector<std::uint32_t> query_validated(std::span<const AabbNode> nodes,const Vec& center,const Vec& half){
    std::vector<std::uint32_t> leaves;std::size_t i{};
    while(i<nodes.size()){
        const auto& n=nodes[i];bool outside=false;
        for(std::size_t k=0;k<3;k++)outside=outside||n.half_extent[k]+half[k]<std::abs(n.center[k]-center[k]);
        if(!outside&&(n.packed&1))leaves.push_back(static_cast<std::uint32_t>(i));
        i+=outside&&!(n.packed&1)?n.packed>>1:1;
    }
    return leaves;
}
struct LocalContact {Vec normal{},penetration{},point_b{};bool face{};};
bool triangle_contact(const Vec& center,float radius,const CookedTriangle& tri,const std::array<Vec,3>& vertices,LocalContact& result){
    const auto& n=tri.normal;const float distance=dot(sub(center,vertices[0]),n);
    if(distance>radius||0.f>distance)return false;
    const float radius_squared=radius*radius;
    const float circle_radius=std::sqrt(radius_squared-distance*distance);
    const float negative_distance=-distance;Vec projection{};
    for(std::size_t k=0;k<3;k++)projection[k]=n[k]*negative_distance+center[k];
    constexpr float small_squared=std::bit_cast<float>(std::uint32_t{0x2edbe6ff});
    for(std::size_t i=0;i<3;i++){
        const auto next=(i+1)%3;auto edge=sub(vertices[next],vertices[i]);const float edge_squared=dot(edge,edge);
        if(edge_squared<=small_squared||edge_squared>=std::numeric_limits<float>::max())return false;
        const float inverse_edge=1.f/std::sqrt(edge_squared);for(float& x:edge)x=x*inverse_edge;
        const auto outward=cross(edge,n);const auto relative=sub(projection,vertices[i]);const float side=dot(outward,relative);
        if(side>circle_radius)return false;
        if(side<=0)continue;
        const float along=dot(edge,relative);Vec point{};bool vertex=false;
        if(along<0){point=vertices[i];vertex=true;}
        else if(dot(edge,sub(projection,vertices[next]))>0){point=vertices[next];vertex=true;}
        else for(std::size_t k=0;k<3;k++)point[k]=(-side)*outward[k]+projection[k];
        const auto delta=sub(center,point);const float squared=dot(delta,delta);
        if(vertex){if(radius_squared<squared||squared<=small_squared)return false;}
        else if(squared<=9.999999747378752e-6f)return false;
        const float length=std::sqrt(squared),inverse=1.f/length;const float factor=(length-radius)*inverse;
        Vec projected_delta{};for(std::size_t k=0;k<3;k++)projected_delta[k]=delta[k]*factor;
        const float penetration=-dot(projected_delta,n);result.point_b=point;
        for(std::size_t k=0;k<3;k++){result.normal[k]=delta[k]*inverse;result.penetration[k]=n[k]*penetration;}
        result.face=false;return true;
    }
    result.normal=n;result.point_b=projection;result.face=true;
    const float penetration=radius-distance;for(std::size_t k=0;k<3;k++)result.penetration[k]=n[k]*penetration;return true;
}
}
std::vector<std::uint32_t> query_aabb_tree(std::span<const AabbNode> nodes,const Vec& center,const Vec& half){
    bounded(center);bounded(half);for(float x:half)require(x>=0,"Negative query AABB half extent");validate_tree(nodes);return query_validated(nodes,center,half);
}
std::vector<CookedTriangle> cook_triangles(std::span<const Vec> vertices,std::span<const IndexedTriangle> triangles){
    require(vertices.size()<=1000000&&triangles.size()<=1000000,"Too many triangles to cook");
    for(const auto& vertex:vertices)bounded(vertex);
    for(const auto& tri:triangles)for(auto index:tri.vertices)require(index<vertices.size(),"Raw triangle vertex out of range");
    std::vector<CookedTriangle> cooked;cooked.reserve(triangles.size());
    for(const auto& tri:triangles){
        const auto& a=vertices[tri.vertices[0]];const auto e1=sub(vertices[tri.vertices[1]],a),e2=sub(vertices[tri.vertices[2]],a);
        auto normal=cross(e1,e2);const float squared=dot(normal,normal);
        if(squared>std::bit_cast<float>(std::uint32_t{0x1e3ce509})){
            const float inverse=1.f/std::sqrt(squared);for(float& x:normal)x=x*inverse;
        }
        const float plane=((-normal[0])*a[0]-normal[1]*a[1])-normal[2]*a[2];
        bounded(normal);bounded(std::array{plane});cooked.push_back({normal,plane,tri.vertices,tri.surface_id,0});
    }
    return cooked;
}
std::vector<AabbPrimitive> triangle_aabbs(std::span<const Vec> vertices,std::span<const IndexedTriangle> triangles){
    require(vertices.size()<=1000000&&triangles.size()<=1000000,"Too many triangle bounds");for(const auto& v:vertices)bounded(v);
    for(const auto& t:triangles)for(auto index:t.vertices)require(index<vertices.size(),"Triangle bound vertex out of range");
    std::vector<AabbPrimitive> result;result.reserve(triangles.size());
    for(std::size_t i=0;i<triangles.size();i++){
        const auto& t=triangles[i];const auto& a=vertices[t.vertices[0]];const auto& b=vertices[t.vertices[1]];const auto& c=vertices[t.vertices[2]];
        AabbPrimitive out{};out.index=static_cast<std::uint32_t>(i);
        for(std::size_t k=0;k<3;k++){
            const float lo=minimum(c[k],minimum(b[k],a[k])),hi=maximum(c[k],maximum(b[k],a[k]));
            out.center[k]=(hi+lo)*.5f;out.half_extent[k]=(hi-lo)*.5f;
        }
        result.push_back(out);
    }
    return result;
}
namespace {
std::size_t partition(std::vector<AabbPrimitive>& p,std::size_t begin,std::size_t end){
    Vec mean{},variance{};
    for(std::size_t i=begin;i<end;i++)for(std::size_t k=0;k<3;k++)mean[k]=mean[k]+p[i].center[k];
    const float inverse=1.f/static_cast<float>(end-begin);for(float& x:mean)x=x*inverse;
    for(std::size_t i=begin;i<end;i++)for(std::size_t k=0;k<3;k++){
        const float d=p[i].center[k]-mean[k];variance[k]=variance[k]+d*d;
    }
    const std::size_t axis=variance[1]>variance[0]?(variance[2]>variance[1]?2:1):(variance[2]>variance[0]?2:0);
    std::size_t split=begin;
    for(std::size_t i=begin;i<end;i++)if(p[i].center[axis]>mean[axis]){std::swap(p[i],p[split]);++split;}
    const auto third=(end-begin)/3;
    if(split<=begin+third||split>=end-third-1)return begin+(end-begin)/2;
    return split;
}
void construct(std::vector<AabbPrimitive>& primitives,std::size_t begin,std::size_t end,std::uint32_t width,std::vector<AabbNode>& nodes){
    if(end-begin<=width){
        for(std::size_t i=begin;i<end;i++)nodes.push_back({primitives[i].center,primitives[i].half_extent,(primitives[i].index<<1)|1u});
        return;
    }
    const auto split=partition(primitives,begin,end);const auto root=nodes.size();
    Vec low{},high{};for(std::size_t k=0;k<3;k++){low[k]=primitives[begin].center[k]-primitives[begin].half_extent[k];high[k]=primitives[begin].center[k]+primitives[begin].half_extent[k];}
    for(std::size_t i=begin+1;i<end;i++)for(std::size_t k=0;k<3;k++){
        low[k]=minimum(primitives[i].center[k]-primitives[i].half_extent[k],low[k]);
        high[k]=maximum(primitives[i].center[k]+primitives[i].half_extent[k],high[k]);
    }
    AabbNode node{};for(std::size_t k=0;k<3;k++){node.center[k]=(high[k]+low[k])*.5f;node.half_extent[k]=(high[k]-low[k])*.5f;}
    nodes.push_back(node);construct(primitives,begin,split,width,nodes);construct(primitives,split,end,width,nodes);
    nodes[root].packed=static_cast<std::uint32_t>((nodes.size()-root)*2);
}
}
std::vector<AabbNode> build_aabb_tree(std::span<const AabbPrimitive> primitives,std::uint32_t leaf_width){
    require(primitives.size()<=1000000&&leaf_width>=1&&leaf_width<=1000000,"Invalid AABB build count/leaf width");
    for(const auto& p:primitives){bounded(p.center);bounded(p.half_extent);for(float x:p.half_extent)require(x>=0,"Negative primitive half extent");require(p.index<=0x7fffffffu,"AABB primitive ID cannot be encoded");}
    auto copy=std::vector<AabbPrimitive>(primitives.begin(),primitives.end());std::vector<AabbNode> nodes;nodes.reserve(primitives.size()*2);
    if(!copy.empty())construct(copy,0,copy.size(),leaf_width,nodes);
    validate_tree(nodes);return nodes;
}
std::vector<MeshContact> collide_sphere_mesh(const Sphere& sphere,const CookedMeshView& mesh,std::uint32_t initial_flags){
    bounded(sphere.center);require(std::isfinite(sphere.radius)&&sphere.radius>=0&&sphere.radius<=1e6f,"Invalid mesh query sphere radius");
    require(mesh.vertices.size()<=1000000&&mesh.triangles.size()<=1000000,"Too much cooked geometry");
    bounded(mesh.transform.rotation);bounded(mesh.transform.translation);validate_tree(mesh.tree);
    for(const auto& vertex:mesh.vertices)bounded(vertex);
    for(const auto& tri:mesh.triangles){bounded(tri.normal);for(auto index:tri.vertices)require(index<mesh.vertices.size(),"Cooked triangle vertex out of range");}
    for(const auto& node:mesh.tree)if(node.packed&1)require((node.packed>>1)<mesh.triangles.size(),"AABB leaf triangle out of range");
    const auto relative=sub(sphere.center,mesh.transform.translation);Vec center{};
    for(std::size_t k=0;k<3;k++)center[k]=(relative[1]*mesh.transform.rotation[3+k]+relative[0]*mesh.transform.rotation[k])+relative[2]*mesh.transform.rotation[6+k];
    bounded(center);const auto candidates=query_validated(mesh.tree,center,{sphere.radius,sphere.radius,sphere.radius});
    std::vector<MeshContact> contacts;
    for(auto leaf:candidates){
        const auto index=mesh.tree[leaf].packed>>1;const auto& tri=mesh.triangles[index];
        const std::array points{mesh.vertices[tri.vertices[0]],mesh.vertices[tri.vertices[1]],mesh.vertices[tri.vertices[2]]};LocalContact local{};
        if(!triangle_contact(center,sphere.radius,tri,points,local))continue;
        MeshContact out{};out.triangle_index=index;out.surface_point_b=world(mesh.transform,local.point_b);out.triangle_normal=rotate(mesh.transform,tri.normal);
        auto& g=out.geometry;g.normal=rotate(mesh.transform,local.normal);g.penetration_vector=rotate(mesh.transform,local.penetration);
        for(std::size_t k=0;k<3;k++)g.surface_point_a[k]=g.normal[k]*(-sphere.radius)+sphere.center[k];
        g.flags=(initial_flags|2u)&~1u;g.flags|=local.face?1u:0u;g.surface_id_a=sphere.surface_id;g.surface_id_b=tri.surface_id;
        bounded(out.surface_point_b);bounded(out.triangle_normal);bounded(g.normal);bounded(g.penetration_vector);bounded(g.surface_point_a);contacts.push_back(out);
    }
    return contacts;
}
}

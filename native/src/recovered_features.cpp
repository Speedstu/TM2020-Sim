#include "tm2020/recovered_features.hpp"
#include <bit>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
void bounded(const ConvexVector& p){for(float x:p)require(std::isfinite(x)&&std::abs(x)<=1e6f,"Convex feature input/output exceeds finite domain");}
float dot(const ConvexVector& a,const ConvexVector& b){return (a[1]*b[1]+a[0]*b[0])+a[2]*b[2];}
void validate(const ConvexTopologyView& shape){
    const auto& a=shape.axes;require(a.vertices.size()<=1000000&&a.face_normals.size()<=1000000&&a.edge_directions.size()<=1000000&&shape.faces.size()<=1000000&&shape.edges.size()<=1000000,"Too many convex topology entries");
    for(const auto& p:a.vertices)bounded(p);
    for(const auto& p:a.face_normals)bounded(p);
    for(const auto& p:a.edge_directions)bounded(p);
    for(const auto& face:shape.faces){require(face.normal_index<a.face_normals.size(),"Convex face normal out of range");require(face.vertices.size()<=1000000,"Too many face vertices");for(auto i:face.vertices)require(i<a.vertices.size(),"Convex face vertex out of range");}
    for(const auto& edge:shape.edges)require(edge.vertex_a<a.vertices.size()&&edge.vertex_b<a.vertices.size()&&edge.direction_index<a.edge_directions.size(),"Convex edge index out of range");
}
float face_score(const ConvexTopologyView& shape,const ConvexFace& face,const ConvexVector& direction){
    auto normal=shape.axes.face_normals[face.normal_index];if(!face.keep_normal)for(float& x:normal)x=-x;return dot(normal,direction);
}
}
std::uint32_t select_edge(const ConvexTopologyView& shape,std::uint32_t group,const ConvexVector& direction){
    validate(shape);bounded(direction);std::uint32_t result=no_convex_feature;float best=-std::numeric_limits<float>::max();
    for(std::size_t i=0;i<shape.edges.size();i++){
        const auto& edge=shape.edges[i];if(edge.direction_index!=group)continue;
        const float a=dot(direction,shape.axes.vertices[edge.vertex_a]),b=dot(direction,shape.axes.vertices[edge.vertex_b]);
        const float score=a<=b?b:a;if(best<=score){best=score;result=static_cast<std::uint32_t>(i);}
    }
    return result;
}
std::uint32_t select_face_from_normal(const ConvexTopologyView& shape,std::uint32_t group,const ConvexVector& direction){
    validate(shape);bounded(direction);require(group<shape.axes.face_normals.size(),"Selected convex normal out of range");
    std::uint32_t result=no_convex_feature;float best=-std::numeric_limits<float>::max();
    for(std::size_t i=0;i<shape.faces.size();i++)if(shape.faces[i].normal_index==group){const float score=face_score(shape,shape.faces[i],direction);if(best<=score){best=score;result=static_cast<std::uint32_t>(i);}}
    return result;
}
std::uint32_t select_incident_face(const ConvexTopologyView& shape,const ConvexVector& direction){
    validate(shape);bounded(direction);std::uint32_t result=no_convex_feature;float best=-std::numeric_limits<float>::max();
    for(std::size_t i=0;i<shape.faces.size();i++){const float score=face_score(shape,shape.faces[i],direction);if(best<=score){best=score;result=static_cast<std::uint32_t>(i);}}
    return result;
}
EdgeFrame edge_frame(const ConvexTopologyView& shape,std::uint32_t index){
    validate(shape);require(index<shape.edges.size(),"Selected convex edge out of range");const auto& edge=shape.edges[index];
    const auto& a=shape.axes.vertices[edge.vertex_a];const auto& b=shape.axes.vertices[edge.vertex_b];EdgeFrame out{};
    for(std::size_t k=0;k<3;k++){out.center[k]=(b[k]+a[k])*.5f;out.direction[k]=b[k]-a[k];}
    const float squared=(out.direction[0]*out.direction[0]+out.direction[1]*out.direction[1])+out.direction[2]*out.direction[2];
    float length=0;if(squared>std::bit_cast<float>(std::uint32_t{0x2edbe6ff})&&squared<std::numeric_limits<float>::max()){
        length=std::sqrt(squared);const float inverse=1.f/length;for(float& x:out.direction)x=x*inverse;
    }
    out.half_length=length*.5f;bounded(out.center);bounded(out.direction);return out;
}
}

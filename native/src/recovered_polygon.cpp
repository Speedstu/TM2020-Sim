#include "tm2020/recovered_polygon.hpp"
#include <bit>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void bounded(const ConvexVector& v){for(float x:v)if(!std::isfinite(x)||std::abs(x)>1e6f)throw std::invalid_argument("Polygon vector exceeds finite domain");}
void validate(const ContactPlane& plane){bounded(plane.normal);if(!std::isfinite(plane.constant)||std::abs(plane.constant)>1e6f)throw std::invalid_argument("Polygon plane exceeds finite domain");}
float dot(const ConvexVector& a,const ConvexVector& b){return (a[1]*b[1]+a[0]*b[0])+a[2]*b[2];}
float distance(const ConvexVector& point,const ContactPlane& plane){return dot(point,plane.normal)+plane.constant;}
PlaneSide side(const ConvexVector& point,const ContactPlane& plane){
    const float d=distance(point,plane);constexpr float band=9.999999747378752e-5f;
    return d>band?PlaneSide::positive:(d< -band?PlaneSide::negative:PlaneSide::on_plane);
}
ConvexVector intersection(const ConvexVector& previous,const ConvexVector& current,const ContactPlane& plane){
    ConvexVector direction{current[0]-previous[0],current[1]-previous[1],current[2]-previous[2]};
    const float squared=dot(direction,direction);
    if(squared>std::bit_cast<float>(std::uint32_t{0x2edbe6ff})&&squared<std::numeric_limits<float>::max()){
        const float inverse=1.f/std::sqrt(squared);for(float& x:direction)x=x*inverse;
    }
    const float denominator=dot(plane.normal,direction);
    if(std::abs(denominator)<=9.999999747378752e-6f)throw std::invalid_argument("Polygon intersection is outside deterministic native domain");
    const float t=(-distance(previous,plane))/denominator;ConvexVector point{};
    for(std::size_t k=0;k<3;k++)point[k]=direction[k]*t+previous[k];
    bounded(point);return point;
}
}
PlaneSide classify_point(const ConvexVector& point,const ContactPlane& plane){bounded(point);validate(plane);return side(point,plane);}
PolygonSplit split_polygon(std::span<const ConvexVector> polygon,const ContactPlane& plane){
    validate(plane);if(polygon.size()>1000000)throw std::invalid_argument("Too many polygon vertices");for(const auto& p:polygon)bounded(p);
    PolygonSplit result;if(polygon.empty())return result;result.positive.reserve(polygon.size()*2);result.negative.reserve(polygon.size()*2);
    auto previous=polygon.back();auto previous_side=side(previous,plane);
    for(const auto& current:polygon){
        const auto current_side=side(current,plane);
        if(current_side==PlaneSide::positive){
            if(previous_side==PlaneSide::negative){const auto p=intersection(previous,current,plane);result.positive.push_back(p);result.negative.push_back(p);}
            result.positive.push_back(current);
        }else if(current_side==PlaneSide::negative){
            if(previous_side==PlaneSide::positive){const auto p=intersection(previous,current,plane);result.positive.push_back(p);result.negative.push_back(p);}
            else if(previous_side==PlaneSide::on_plane)result.negative.push_back(previous);
            result.negative.push_back(current);
        }else{
            result.positive.push_back(current);if(previous_side==PlaneSide::negative)result.negative.push_back(current);
        }
        previous=current;previous_side=current_side;
    }
    return result;
}
std::vector<ConvexVector> face_contacts(std::span<const ConvexVector> incident,
    std::span<const ConvexVector> reference,const ConvexVector& reference_normal,
    const std::array<float,12>& transform,bool keep_normal){
    if(incident.size()<3||reference.size()<3||incident.size()>4096||reference.size()>4096)
        throw std::invalid_argument("Contact faces require 3..4096 vertices");
    for(const auto& p:incident)bounded(p);
    for(const auto& p:reference)bounded(p);
    bounded(reference_normal);
    for(float x:transform)if(!std::isfinite(x)||std::abs(x)>1e6f)throw std::invalid_argument("Contact transform exceeds finite domain");
    const auto rotate=[&](const ConvexVector& p){
        ConvexVector result{};
        for(std::size_t k=0;k<3;k++)result[k]=(p[0]*transform[k*3]+p[1]*transform[k*3+1])+p[2]*transform[k*3+2];
        return result;
    };
    const auto apply=[&](const ConvexVector& p){auto result=rotate(p);for(std::size_t k=0;k<3;k++)result[k]=result[k]+transform[9+k];bounded(result);return result;};
    auto normal=rotate(reference_normal);if(!keep_normal)for(float& x:normal)x=-x;bounded(normal);
    const auto first=apply(reference.front());auto previous=first;
    std::vector<ConvexVector> polygon(incident.begin(),incident.end()),scratch;
    for(std::size_t j=0;j<reference.size();j++){
        const auto current=apply(reference[(j+1)%reference.size()]);
        ConvexVector edge{current[0]-previous[0],current[1]-previous[1],current[2]-previous[2]};
        const float squared=(edge[0]*edge[0]+edge[1]*edge[1])+edge[2]*edge[2];
        if(squared>std::bit_cast<float>(std::uint32_t{0x2edbe6ff})&&squared<std::numeric_limits<float>::max()){
            const float inverse=1.f/std::sqrt(squared);for(float& x:edge)x=x*inverse;
        }
        ContactPlane plane{{normal[1]*edge[2]-normal[2]*edge[1],normal[2]*edge[0]-normal[0]*edge[2],normal[0]*edge[1]-normal[1]*edge[0]},0};
        plane.constant=((-plane.normal[0])*previous[0]-previous[1]*plane.normal[1])-previous[2]*plane.normal[2];
        // Native split returns before clearing its output when input is empty.
        // The caller reuses two buffers, so an empty intermediate resurrects the
        // older buffer on the next swap. Preserve this observed behavior.
        if(!polygon.empty())scratch=split_polygon(polygon,plane).positive;
        if(scratch.size()>incident.size()+reference.size())throw std::invalid_argument("Faces exceed native convex clipping capacity");
        polygon.swap(scratch);
        previous=current;
    }
    const float constant=((-normal[0])*first[0]-normal[1]*first[1])-normal[2]*first[2];
    std::vector<ConvexVector> result;result.reserve(polygon.size());
    for(const auto& point:polygon){
        const float d=((point[0]*normal[0]+point[1]*normal[1])+point[2]*normal[2])+constant;
        if(d<=0)result.push_back(point);
    }
    return result;
}
}

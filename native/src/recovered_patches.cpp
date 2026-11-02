#include "tm2020/recovered_patches.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void bounded(const ConvexVector& v){for(float x:v)if(!std::isfinite(x)||std::abs(x)>1e6f)throw std::invalid_argument("Contact patch geometry exceeds finite domain");}
bool same_patch(const ConvexContact& a,const ConvexContact& b){
    return (a.normal[1]*b.normal[1]+a.normal[0]*b.normal[0])+a.normal[2]*b.normal[2]>=.999f&&
        (a.surface_id_a&255)==(b.surface_id_a&255)&&(a.surface_id_b&255)==(b.surface_id_b&255);
}
}
std::vector<ContactPatch> build_contact_patches(std::span<const ConvexContact> geometry,
    const SurfaceMaterialTable& materials,const SurfaceObject& a,const SurfaceObject& b,std::uint32_t runtime,
    const SurfaceResponseParameters& parameters){
    if(geometry.size()>1000000)throw std::invalid_argument("Too many contact patch inputs");
    for(const auto& g:geometry){bounded(g.normal);bounded(g.penetration_vector);bounded(g.world_point);if((g.surface_id_a&255)>=80||(g.surface_id_b&255)>=80)throw std::invalid_argument("Uninitialized contact surface material");}
    std::vector<ContactPatch> out;
    struct Run {std::size_t begin{},end{},root{};std::vector<std::size_t> linked;};
    for(std::size_t chunk=0;chunk<geometry.size();chunk+=255){
        const auto end=std::min(geometry.size(),chunk+255);std::vector<Run> runs;
        for(std::size_t j=chunk;j<end;j++){
            if(!runs.empty()&&same_patch(geometry[runs.back().begin],geometry[j])){runs.back().end=j+1;continue;}
            const auto current=runs.size();std::size_t root=current;
            for(std::size_t old=0;old<current;old++)if(runs[old].root==old&&same_patch(geometry[runs[old].begin],geometry[j])){root=old;break;}
            runs.push_back({j,j+1,root,{}});if(root!=current)runs[root].linked.push_back(current);
        }
        for(std::size_t r=0;r<runs.size();r++)if(runs[r].root==r){
            const auto& first=geometry[runs[r].begin];ContactPatch patch{};patch.normal=first.normal;patch.first_chunk=chunk==0;
            patch.response=surface_response(materials,first.surface_id_a,first.surface_id_b,a,b,runtime,parameters);
            const auto emit=[&](const Run& run){for(std::size_t j=run.begin;j<run.end;j++){
                const auto& g=geometry[j];const auto& p=g.penetration_vector;const float depth=std::sqrt((p[0]*p[0]+p[1]*p[1])+p[2]*p[2]);
                patch.points.push_back({g.world_point,depth});
            }};
            emit(runs[r]);for(auto linked:runs[r].linked)emit(runs[linked]);out.push_back(std::move(patch));
        }
    }
    return out;
}
}

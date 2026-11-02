#include "tm2020/recovered_material.hpp"
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void scalar(float x){if(!std::isfinite(x)||std::abs(x)>1e6f)throw std::invalid_argument("Surface response exceeds finite domain");}
}
SurfaceMaterialTable::SurfaceMaterialTable(){
    values.fill({1,.5f});for(auto id:{3,9,10,11,68})values[static_cast<std::size_t>(id)]={0,0};
    values[10].restitution=-.5f;values[23].restitution=.95f;
    values[24].restitution=.8f;values[25].restitution=.8f;values[78].restitution=0;
}
float combine_restitution(float a,float b){
    scalar(a);scalar(b);float result{};
    if(a>0)result=b>0?b*a:b;
    else result=b>0?a:b+a;
    scalar(result);return result;
}
SurfaceResponse surface_response(const SurfaceMaterialTable& table,std::uint16_t material_a,std::uint16_t material_b,
    const SurfaceObject& a,const SurfaceObject& b,std::uint32_t runtime_class_id,const SurfaceResponseParameters& p){
    const auto ia=material_a&0xffu,ib=material_b&0xffu;
    if(ia>=table.values.size()||ib>=table.values.size())throw std::invalid_argument("Surface material low-byte ID outside initialized table");
    for(float x:{p.default_friction,p.vehicle_pair_friction,p.vehicle_pair_restitution,p.dynamic_class_friction,p.special_a_friction})scalar(x);
    SurfaceResponse response{p.default_friction,combine_restitution(table.values[ia].restitution,table.values[ib].restitution)};
    const bool vehicle_a=a.class_id==0x0a020000,vehicle_b=b.class_id==0x0a020000;
    if(vehicle_a&&vehicle_b)return {p.vehicle_pair_friction,p.vehicle_pair_restitution};
    if((vehicle_a&&b.category==0)||(vehicle_b&&a.category==0)){
        const auto variant=vehicle_a?a.vehicle_variant:b.vehicle_variant;
        if(variant==13)return {.175f,.1f};
        response.friction=variant==9?.55f:.125f;
    }else if((a.class_id==runtime_class_id&&b.category==0)||(b.class_id==runtime_class_id&&a.category==0))response.friction=p.dynamic_class_friction;
    else if(a.class_id==0x0a0aa000)response.friction=p.special_a_friction;
    return response;
}
}

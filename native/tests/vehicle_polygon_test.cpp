#include "tm2020/recovered_vehicle.hpp"
#include "tm2020/recovered_polygon.hpp"
#include "tm2020/recovered_material.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
int main()try{
    const std::array<CurvePoint,3> curve{{{0,0},{1,1},{2,0}}};
    check(evaluate_curve(curve,-1)==0&&evaluate_curve(curve,3)==0,"Curve endpoint clamping changed");
    check(evaluate_curve(curve,.5f)==.5f&&evaluate_curve(curve,.5f,1)==0&&evaluate_curve(curve,.5f,2)==.5f,"Curve interpolation mode changed");
    check(evaluate_curve(curve,.5f,0x10)>.5f&&evaluate_curve({},1)==0,"Curve Hermite or empty semantics wrong");
    bool rejected=false;try{evaluate_curve(std::array<CurvePoint,2>{{{1,0},{1,1}}},1,0x10);}catch(const std::invalid_argument&){rejected=true;}check(rejected,"Non-increasing curve accepted");
    RigidState pose{};pose.position={10,20,30};ForceAccumulator forces{};
    apply_local_force_at_point(forces,pose,{0,0,0},{0,10,0},{1,0,0});
    check(forces.linear==std::array{0.f,10.f,0.f}&&forces.angular==std::array{0.f,0.f,10.f},"Off-center force torque wrong");
    std::array<SuspensionWheelState,4> wheels{};for(auto& wheel:wheels)wheel={.1f,.5f,true};
    const SuspensionParameters parameters{2,true,40,1,.2f};
    forces={};check(apply_suspension_mode2(forces,pose,{},{1,0,0},parameters,wheels,0),"Contact spring not applied");
    check(forces.linear[1]==3.5f&&forces.angular[2]==3.5f,"Spring force/torque mismatch");
    const auto saved=forces;wheels[3].contact=false;
    check(!apply_suspension_mode2(forces,pose,{},{1,0,0},parameters,wheels,0)&&std::memcmp(&saved,&forces,sizeof(forces))==0,"All-contact spring gate mutated accumulator");
    rejected=false;try{apply_local_force_at_point(forces,pose,{},{1e6f,1e6f,1e6f},{1e6f,-1e6f,1e6f});}catch(const std::invalid_argument&){rejected=true;}
    check(rejected&&std::memcmp(&saved,&forces,sizeof(forces))==0,"Force overflow partially committed");
    const ContactPlane plane{{1,0,0},0};
    check(classify_point({1e-4f,0,0},plane)==PlaneSide::on_plane&&classify_point({-1e-4f,0,0},plane)==PlaneSide::on_plane,"Plane tolerance boundary changed");
    const std::array<ConvexVector,4> square{{{-1,-1,-.5f},{1,-1,-.5f},{1,1,-.5f},{-1,1,-.5f}}};
    const auto split=split_polygon(square,plane);check(split.positive.size()==4&&split.negative.size()==4,"Square clipping wrong");
    const std::array<ConvexVector,4> reference{{{-2,-2,0},{2,-2,0},{2,2,0},{-2,2,0}}};
    const auto contacts=face_contacts(square,reference,{0,0,1},{1,0,0,0,1,0,0,0,1,0,0,0});
    check(contacts.size()==square.size()&&std::memcmp(contacts.data(),square.data(),sizeof(square))==0,"Face clip/filter changed retained incident loop");
    const SurfaceMaterialTable materials;
    check(materials.values[10].restitution==-.5f&&materials.values[23].restitution==.95f,"Original material initialization defaults changed");
    check(combine_restitution(.5f,.5f)==.25f&&combine_restitution(-.5f,.5f)==-.5f&&combine_restitution(-.5f,-.5f)==-1,"Material combination branches wrong");
    const SurfaceObject vehicle{0x0a020000,13,1},ground{0x0a030000,0,0};
    const auto response=surface_response(materials,0x2301,0xff02,vehicle,ground,0x30abc000);
    check(response.friction==.175f&&response.restitution==.1f,"Vehicle variant surface override wrong");
    const auto pair=surface_response(materials,0,0,vehicle,vehicle,0x30abc000);
    check(pair.friction==0&&pair.restitution==.25f,"Vehicle pair material override wrong");
    rejected=false;try{surface_response(materials,80,0,vehicle,ground,0x30abc000);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected,"Uninitialized low-byte material ID accepted");
    ForceAccumulator auxiliary{};auxiliary.angular={1,2,3};apply_local_force(auxiliary,{}, {2,3,4});
    check(auxiliary.linear==std::array{2.f,3.f,4.f}&&auxiliary.angular==std::array{1.f,2.f,3.f},"Local center force created torque");
    const AuxiliaryVehicleForceParameters tuning{2,1,1,1};AuxiliaryVehicleForceState aux_state{{5,0,10},1,.2f,0,0};
    auxiliary={};apply_auxiliary_vehicle_forces(auxiliary,{}, {},aux_state,tuning,{},2);
    check(auxiliary.linear==std::array{-1.f,0.f,-2.f}&&auxiliary.angular==std::array{0.f,0.f,0.f},"Native center drag branch wrong");
    aux_state.state_word_1370=4;auxiliary={};apply_auxiliary_vehicle_forces(auxiliary,{}, {},aux_state,tuning,{},2);check(auxiliary.linear==std::array{0.f,0.f,0.f},"State bit 4 failed to suppress center drag");
    aux_state={{5,0,10},1,0,0,0};const std::array<AuxiliaryWheelForcePoint,1> aux_wheels{{{{0,0,1},1}}};
    apply_auxiliary_vehicle_forces(auxiliary,{}, {},aux_state,tuning,aux_wheels,1);check(auxiliary.linear[0]>0&&auxiliary.angular[1]==auxiliary.linear[0],"Auxiliary wheel force/torque branch wrong");
    aux_state.local_velocity[2]=6;const auto aux_saved=auxiliary;apply_auxiliary_vehicle_forces(auxiliary,{}, {},aux_state,tuning,aux_wheels,1);
    check(std::memcmp(&aux_saved,&auxiliary,sizeof(auxiliary))==0,"Inclusive native speed threshold changed accumulator");
    rejected=false;try{apply_auxiliary_vehicle_forces(auxiliary,{}, {},aux_state,{2,-1,1,1},aux_wheels,1);}catch(const std::invalid_argument&){rejected=true;}check(rejected&&std::memcmp(&aux_saved,&auxiliary,sizeof(auxiliary))==0,"Invalid force denominator input mutated accumulator");
    std::cout<<"PASS VEHICLE_POLYGON curve_modes=true local_force_torque=true complete_mode2_branch=true polygon_contacts=true transactional_guards=true full_vehicle=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

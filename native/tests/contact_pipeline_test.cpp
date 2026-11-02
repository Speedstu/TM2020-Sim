#include "tm2020/recovered_collision.hpp"
#include "tm2020/recovered_position.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b,const char* text){if(!b)throw std::runtime_error(text);}
int main()try{
    Sphere a{{0,0,0},1,3},b{{2,0,0},1,4};SphereContact contact{};contact.flags=7;
    const auto before=contact;check(!collide_spheres(a,b,contact)&&std::memcmp(&before,&contact,sizeof(contact))==0,"Tangency produced contact");
    b.center={1,0,0};check(collide_spheres(a,b,contact)&&contact.normal[0]==-1&&contact.penetration_vector[0]==-1&&contact.flags==4,"Sphere contact geometry wrong");
    b.center={};b.radius=.25f;contact.flags=7;check(collide_spheres(a,b,contact)&&contact.penetration_vector[1]==-.25f&&contact.flags==7,"Coincident fallback changed native semantics");
    std::array<RigidState,2> states{};states[0].linear_velocity={2,-2,0};
    const std::array<VelocityCoefficients,2> coeff{{{.1f,.1f,.1f,1},{.1f,.1f,.1f,1}}};
    ContactPoint input{0,1,{0,-1,0},{0,1,0},.1f,.5f,.5f};
    auto prepared=prepare_static_contact(input,states,coeff,.01f,1);
    check(prepared.friction_count==2&&prepared.normal.target==-1,"Contact restitution target wrong");
    std::array normal{prepared.normal};auto friction=prepared.friction;
    solve_static_unilateral(states,normal);solve_static_friction(states,friction,normal);
    check(std::abs(states[0].linear_velocity[1]-1)<1e-6f,"Restitution response wrong");
    check(std::abs(states[0].linear_velocity[0])<2,"Tangent friction did not slow body");
    // Prepared positions use a separate format; solving them does not change
    // velocity or substitute for the collision backend's next contact update.
    const auto velocity=states[0].linear_velocity;const auto old_y=states[0].position[1];
    const std::array positions{prepared.position};solve_static_positions(states,coeff,positions,{0,.1f,.2f});
    check(states[0].position[1]>old_y&&states[0].linear_velocity==velocity,"Position solve changed velocity/direction");
    for(unsigned j=0;j<100;j++){
        const auto y=states[0].position[1];solve_static_positions(states,coeff,positions,{0,.1f,.2f});
        check(states[0].position[1]>=y,"Position iterations increased penetration");
    }
    check(std::abs(states[0].position[1]-.1f)<1e-5f,"Position iterations did not resolve prepared penetration");
    const auto checkpoint=states;
    auto invalid=positions;invalid[0].body=3;bool denied=false;
    try{solve_static_positions(states,coeff,invalid,{0,.1f,.2f});}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(states.data(),checkpoint.data(),sizeof(states))==0,"Invalid position body partly committed");
    std::array partial{prepared.position,StaticPositionConstraint{0,{0,1,0},{-1e6f,1,0},{1,0,0}}};denied=false;
    try{solve_static_positions(states,coeff,partial,{0,1e6f,1e6f});}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(states.data(),checkpoint.data(),sizeof(states))==0,"Late position-domain failure partly committed");
    auto rotation=states[0];const auto prior=rotation;denied=false;
    try{correct_rotation(rotation,{2,0,0});}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(&rotation,&prior,sizeof(rotation))==0,"Out-of-domain rotation partly committed");
    rotation.quaternion={};correct_rotation(rotation,{.01f,0,0});check(rotation.quaternion==std::array{1.f,0.f,0.f,0.f},"Degenerate quaternion fallback wrong");
    const auto zero=rotation;correct_rotation(rotation,{1e-7f,0,0});check(std::memcmp(&zero,&rotation,sizeof(rotation))==0,"Tiny correction changed orientation");
    std::cout<<"PASS CONTACT_PIPELINE geometry=true restitution=true friction=true penetration_convergence=true late_transactional_rejection=true full_vehicle_physics=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

#include "tm2020/recovered_jacobian.hpp"
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
int main()try{
    DynamicJacobian jac{};jac.accumulated_impulse=3;
    prepare_dynamic_jacobian(jac,{0,0,0,1},{0,0,0,1},{0,0,0},{0,0,0},{0,-1,0},0);
    check(jac.effective_coefficient==.5f&&jac.accumulated_impulse==3,"Jacobian preparation changed impulse/denominator");
    jac.accumulated_impulse=0;
    std::array<RigidState,2> states{};states[0].linear_velocity={0,-2,0};
    std::array<DynamicJacobianConstraint,1> normals{{{0,1,{0,-1,0},jac}}};
    check(solve_dynamic_unilateral(states,normals),"Normal impulse missing");
    check(states[0].linear_velocity[1]==-1&&states[1].linear_velocity[1]==-1,"Normal momentum transfer wrong");
    check(normals[0].jacobian.accumulated_impulse==1&&!solve_dynamic_unilateral(states,normals),"Normal convergence wrong");
    std::array<DynamicFrictionConstraint,1> friction{};auto& f=friction[0];f.constraint={0,1,{1,0,0},jac};f.friction=.25f;
    states[0].linear_velocity[0]=2;
    check(solve_dynamic_friction(states,friction,normals),"Friction impulse missing");
    check(f.constraint.jacobian.accumulated_impulse==.25f&&states[0].linear_velocity[0]==1.75f&&states[1].linear_velocity[0]==.25f,"Friction cap wrong");
    normals[0].jacobian.accumulated_impulse=0;
    check(solve_dynamic_friction(states,friction,normals)&&f.constraint.jacobian.accumulated_impulse==0,"Zero normal load failed to release friction");
    std::array<StaticJacobianConstraint,1> fixed{};fixed[0].direction={0,-1,0};fixed[0].inverse_mass=1;fixed[0].effective_coefficient=1;
    states[0].linear_velocity={2,-2,0};solve_static_unilateral(states,fixed);
    check(states[0].linear_velocity[1]==0&&fixed[0].accumulated_impulse==2,"Static impact wrong");
    std::array<StaticFrictionConstraint,1> sf{};sf[0].constraint=fixed[0];sf[0].constraint.direction={1,0,0};sf[0].constraint.accumulated_impulse=0;sf[0].friction=.25f;
    solve_static_friction(states,sf,fixed);check(states[0].linear_velocity[0]==1.5f,"Static friction wrong");
    const auto before=states;const auto before_sf=sf;sf[0].normal_index=2;bool rejected=false;
    try{solve_static_friction(states,sf,fixed);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected&&std::memcmp(states.data(),before.data(),sizeof(states))==0&&sf[0].constraint.accumulated_impulse==before_sf[0].constraint.accumulated_impulse,"Bad normal index partly committed");
    auto old=jac;rejected=false;
    try{prepare_dynamic_jacobian(jac,{},{},{},{},{1,0,0},0);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected&&std::memcmp(&old,&jac,sizeof(jac))==0,"Singular preparation partly committed");
    // Failure generated after a valid first row must also roll back both rows.
    std::array<StaticJacobianConstraint,2> huge{fixed[0],fixed[0]};huge[0].accumulated_impulse=0;huge[1].inverse_mass=1e6f;huge[1].effective_coefficient=1e6f;huge[1].direction={1,0,0};
    const auto old_huge=huge;rejected=false;
    try{solve_static_unilateral(states,huge);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected&&std::memcmp(states.data(),before.data(),sizeof(states))==0&&std::memcmp(huge.data(),old_huge.data(),sizeof(huge))==0,"Overflow partly committed batch");
    std::cout<<"PASS JACOBIAN friction_cap=true load_release=true convergence=true transactional_rejection=true complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

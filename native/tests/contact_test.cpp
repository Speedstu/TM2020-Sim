#include "tm2020/recovered_contacts.hpp"
#include "tm2020/recovered_step.hpp"
#include <cmath>
#include <bit>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b,const char* message){if(!b)throw std::runtime_error(message);}
int main()try{
    std::array<RigidState,2> states{};const std::array<VelocityCoefficients,2> coefficients{{{0,0,0,1},{0,0,0,1}}};
    states[0].linear_velocity={0,-1,0};states[1].linear_velocity={0,1,0};
    std::array<DynamicNormalConstraint,1> contacts{{{0,1,{0,0,0},{0,1,0},0,.5f,0}}};
    const auto delta=solve_dynamic_normals(states,coefficients,contacts);
    check(delta==1&&states[0].linear_velocity[1]==0&&states[1].linear_velocity[1]==0,"Equal-mass impact impulse wrong");
    check(contacts[0].accumulated_impulse==1,"Accumulated impulse lost");
    check(solve_dynamic_normals(states,coefficients,contacts)==0,"Converged contact changed");
    states[0].linear_velocity={0,-2,0};std::array<StaticNormalConstraint,1> fixed{{{0,{0,0,0},{0,1,0},0,1,0}}};
    solve_static_normals(states,coefficients,fixed);check(states[0].linear_velocity[1]==0&&fixed[0].accumulated_impulse==2,"Static impact wrong");
    auto before=states;auto invalid=fixed;invalid[0].body=2;bool denied=false;
    try{solve_static_normals(states,coefficients,invalid);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(states.data(),before.data(),sizeof(states))==0,"Invalid index partly mutated states");
    check(select_pose_fraction({0,0,0},0,.01f)==.01f,"Resting body was subdivided");
    check(select_pose_fraction({100,0,0},0,.01f)==.1f*.01f,"Minimum fraction changed");
    check(select_pose_fraction({100,0,0},.5f,.01f)==.5f*.01f,"Interior fraction wrong");
    std::array<SuspensionWheelState,4> wheels{};for(auto& w:wheels)w={.1f,2,true};
    const SuspensionParameters spring{2,false,40,1,.2f};float force=123;
    check(suspension_mode2(spring,wheels,0,force)&&force==2,"Spring/damper order wrong");
    wheels[0].contact=false;force=123;check(!suspension_mode2(spring,wheels,0,force)&&force==123,"Inactive suspension wrote force");
    auto all=spring;all.require_all_contacts=true;check(!suspension_mode2(all,wheels,1,force),"All-contact gate ignored");
    auto nan=spring;nan.stiffness=std::numeric_limits<float>::quiet_NaN();denied=false;
    try{suspension_mode2(nan,wheels,1,force);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&force==123,"Invalid spring input changed output");
    SolverParameters solver;solver.use_constraints2=0x7f800001;
    const auto step=prepare_step_parameters(.01f,{0,-9.81f,0},solver,0x12345678,0x87654321);
    check(step.inverse_interval==100.f&&step.gravity_magnitude==9.81f&&step.use_constraints2==0x7f800001&&step.opaque_24==0x12345678&&step.opaque_28==0x87654321,"Step context words or gravity changed");
    check(step.decay_multiplier>0&&step.decay_multiplier<1,"Invalid step decay");
    for(float interval:{0.f,-.01f,1.01f}){
        denied=false;try{prepare_step_parameters(interval,{0,0,0},solver,0,0);}catch(const std::invalid_argument&){denied=true;}
        check(denied,"Out-of-domain step interval accepted");
    }
    check(std::bit_cast<std::uint32_t>(approximate_power_of_two(-200.f))==std::bit_cast<std::uint32_t>(approximate_power_of_two(-126.f)),"Native exponent lower clamp changed");
    std::cout<<"PASS PREPARED_CONTACTS conservation=true convergence=true transactional_rejection=true subdivision=true conditional_suspension=true complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

#include "tm2020/recovered_solver.hpp"
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b,const char* why){if(!b)throw std::runtime_error(why);}
int main()try{
    const std::array<VelocityCoefficients,2> coefficients{{{1,1,1,.5f},{1,1,1,.5f}}};std::array<RigidState,2> initial{};initial[0].linear_velocity={2,0,0};
    PointConstraint point{0,fixed_constraint_body,{},{},{1,0,0},0,1,.5f,0};std::array points{point};auto states=initial;
    check(solve_point_constraints(states,coefficients,points)==1&&points[0].accumulated_impulse==-1&&states[0].linear_velocity[0]==1.5f,"Signed point constraint did not retain negative impulse");
    point.softness=0;points[0]=point;states=initial;check(solve_point_constraints(states,coefficients,points)==0&&states[0].linear_velocity[0]==2,"Zero-softness point constraint lost native unilateral clamp");
    states={};states[0].angular_velocity={2,0,0};std::array<AngularConstraint,1> angular{{{0,fixed_constraint_body,{1,0,0},0,0,1,0}}};
    check(solve_angular_constraints(states,coefficients,angular)==2&&states[0].angular_velocity[0]==1,"Angular solver did not use coefficient lane 3");
    states={};states[0].angular_velocity={2,3,4};std::array<AngularCouplingConstraint,1> couplings{{{0,1,{1,0,0},{1,0,0},{1,0,0},{1,0,0},1}}};
    solve_angular_couplings(states,coefficients,couplings);check(states[0].angular_velocity==std::array{1.f,0.f,0.f}&&states[1].angular_velocity==std::array{-1.f,0.f,0.f},"Native coupling projection/rate relation wrong");
    states={};states[0].angular_velocity={.0005f,2,3};const auto small=states;couplings[0].coefficient_weights_a={};solve_angular_couplings(states,coefficients,couplings);check(std::memcmp(states.data(),small.data(),sizeof(states))==0,"Sub-threshold coupling should skip singular weights without changing state");
    states=initial;std::array<ConstraintIsland,1> islands{};point.softness=1;islands[0].early_points.push_back(point);islands[0].late_points.push_back({8,fixed_constraint_body,{},{},{1,0,0},0,1,.5f,0});
    bool denied=false;try{solve_constraint_islands(states,coefficients,islands,{0,0,1});}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(states.data(),initial.data(),sizeof(states))==0&&islands[0].early_points[0].accumulated_impulse==0,"Late joint island failure partly committed earlier joint impulse");
    islands[0].late_points.clear();solve_constraint_islands(states,coefficients,islands,{0,0,1});check(states[0].linear_velocity[0]==1.5f&&islands[0].early_points[0].accumulated_impulse==-1,"General joint island failed to run early point pass");
    const std::array<AngularCouplingConstraint,2> invalid{{{0,1,{1,0,0},{1,0,0},{1,0,0},{1,0,0},1},{0,1,{1,0,0},{1,0,0},{},{1,0,0},2}}};
    states[0].angular_velocity={2,0,0};states[1].angular_velocity={};const auto saved=states;denied=false;try{solve_angular_couplings(states,coefficients,invalid);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(states.data(),saved.data(),sizeof(states))==0,"Singular late coupling partly committed earlier angular update");
    std::cout<<"PASS JOINTS signed_and_unilateral=true fixed_bodies=true angular_lane3=true threshold=true native_island_pass=true transactional_rejection=true joint_construction=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

#include "tm2020/recovered_joint_position.hpp"
#include "tm2020/recovered_frames.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b,const char* why){if(!b)throw std::runtime_error(why);}
bool near(float a,float b){return std::abs(a-b)<1e-5f;}
int main()try{
    std::array<RigidState,2> states{};std::array<ProjectionPositionConstraint,1> projections{{{0,fixed_constraint_body,1,{2,0,0},{1,0,0}}}};
    solve_projection_positions(states,projections);check(states[0].position[0]==1,"Fixed projection upper bound translation wrong");
    states={};states[1].position[0]=3;projections[0]={0,1,1,{},{1,0,0}};solve_projection_positions(states,projections);check(states[0].position[0]==1&&states[1].position[0]==2,"Dynamic projection did not split error in half");
    states={};std::array<AnchoredPositionConstraint,1> anchors{{{0,fixed_constraint_body,{1,0,0},{},0,{2,0,0},{1,0,0}}}};solve_anchor_positions(states,anchors);check(near(states[0].position[0],1.05f),"Anchored solver did not scale local A by 0.95");
    states={};states[1].position[0]=3;anchors[0]={0,1,{},{},1,{},{1,0,0}};solve_anchor_positions(states,anchors);check(near(states[0].position[0],.2f)&&near(states[1].position[0],2.8f),"Dynamic anchored correction did not retain native 0.1 factor");
    std::array<RigidState,1> single{};single[0].quaternion={.5f,-.5f,.5f,.5f};single[0].rotation={2,0,0,0,3,0,0,0,4};const auto matrix=single[0].rotation;
    const std::array<QuaternionAxisConstraint,1> axes{{{0,0,{1,0,0},0,{1,0,0,0}}}};solve_quaternion_axes(single,axes);
    check(single[0].quaternion[0]<0&&single[0].quaternion[1]>0&&single[0].quaternion[2]==0&&single[0].quaternion[3]==0&&single[0].rotation==matrix,"Quaternion sign/projection or preserved stale matrix differs");
    single[0].quaternion={1e6f,1e6f,1e6f,1e6f};solve_quaternion_axes(single,axes);check(single[0].quaternion==std::array{1.f,0.f,0.f,0.f},"Large relative quaternion fallback changed");
    std::array<float,3> v{1,0,0};const float h=std::sqrt(.5f);rotate_vector_quaternion(v,{h,0,h,0});check(std::abs(v[0])<1e-5f&&near(v[2],-1),"Quaternion vector rotation orientation wrong");
    single={};const std::array<VelocityCoefficients,1> coefficients{{{.1f,.1f,.1f,1}}};std::array<PositionIsland,2> islands{};
    islands[0].static_projection.push_back({0,fixed_constraint_body,1,{5,0,0},{1,0,0}});islands[1].static_anchors.push_back({0,fixed_constraint_body,{},{},0,{2,0,0},{1,0,0}});
    solve_position_islands(single,coefficients,islands,1,{0,.1f,.2f});check(single[0].position[0]==2,"Position scheduler grouped pass types across islands instead of completing each island");
    const auto before=single;islands[1].static_contacts.push_back({8,{},{},{1,0,0}});bool denied=false;
    try{solve_position_islands(single,coefficients,islands,1,{0,.1f,.2f});}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(before.data(),single.data(),sizeof(single))==0,"Late position-island error partly committed earlier passes");
    solve_position_islands(single,coefficients,islands,0,{0,.1f,.2f});check(std::memcmp(before.data(),single.data(),sizeof(single))==0,"Zero position iterations changed state");
    std::array<RigidState,2> framed{};const std::array<std::array<float,3>,2> centers{{{1,2,3},{4,5,6}}};shift_model_center_frame(framed,centers,false);check(framed[0].position==centers[0]&&framed[1].position==centers[1],"Model center frame addition wrong");shift_model_center_frame(framed,centers,true);check(framed[0].position==std::array{0.f,0.f,0.f},"Model center frame subtraction wrong");
    framed[1].rotation[0]=1e6f;auto huge_centers=centers;huge_centers[1][0]=1e6f;const auto saved=framed;denied=false;try{shift_model_center_frame(framed,huge_centers,false);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(framed.data(),saved.data(),sizeof(framed))==0,"Late center-frame overflow partly committed earlier body");
    std::cout<<"PASS JOINT_POSITION projection_bounds=true anchored_native_factors=true quaternion_sign_and_matrix_preservation=true per_island_order=true model_frame=true transactional=true whole_game_step=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

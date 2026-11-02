#include "tm2020/recovered_wheel.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b,const char* why){if(!b)throw std::runtime_error(why);}
bool near(float a,float b){return std::abs(a-b)<1e-5f;}
int main()try{
    WheelKinematicState state{.1f,0,0,0,{0,2,0},-1608.4954833984375f,1,7,1,0};MeshTransform pose{};
    WheelKinematicParameters p{2,.2f,.5f,10,.5f,20,3,false,false,{}};WheelKinematicInput input{{1,1,0},false,.5f,0,0,10};
    update_wheel_kinematics(state,pose,input,p,{},.01f);
    check(state.phase_78==0&&state.normal_44==std::array{0.f,1.f,0.f}&&state.angle_7c==0&&state.target_angle_80==7,"Wheel phase/normal/disabled-model semantics wrong");
    check(near(state.length,.11f)&&near(state.speed,1)&&near(pose.translation[1],1.39f),"Mode 2 wheel spring recovery/pose wrong");
    std::array<SuspensionWheelState,4> wheels{};for(auto& w:wheels)w={state.length,state.speed,true};ForceAccumulator force{};
    check(apply_suspension_mode2(force,{}, {},{1,0,0},{2,true,40,1,.2f},wheels,0)&&near(force.linear[1],2.6f)&&near(force.angular[2],2.6f),"Kinematic wheel state did not feed recovered spring force/torque");
    p.suspension_mode_238=3;state.length=.2f;state.pending_compression=.3f;update_wheel_kinematics(state,pose,input,p,{},.01f);
    check(near(state.length,.1f)&&near(state.speed,-100)&&near(pose.translation[1],1.4f)&&state.pending_compression==0,"Mode 3 compression clamp/speed/pose wrong");
    p.suspension_mode_238=0;const auto saved_pose=pose;state.angle_7c=0;input.model_word_4=true;input.blend_1c3c=1;state.contact_word_34=0;
    update_wheel_kinematics(state,pose,input,p,{},.01f);check(near(state.angle_7c,-.03f)&&near(state.target_angle_80,-.2617994f)&&std::memcmp(&saved_pose,&pose,sizeof(pose))==0,"Airborne default angle slew or preserved mode 0 pose wrong");
    const std::array<CurvePoint,2> material_curve{{{0,20},{100,20}}};const std::array<WheelSteeringMaterial,1> materials{{{5,{material_curve,0}}}};
    p.material_parameters_1a48=true;state.material_40=14;p.remap_material14_to0=true;state.contact_word_34=1;state.angle_7c=0;input.blend_1c3c=0;input.blend_1c44=1;
    update_wheel_kinematics(state,pose,input,p,materials,.01f);check(near(state.target_angle_80,-.1745329f),"Contact material curve was incorrectly gated by empty global curve");
    state.contact_word_34=0;state.angle_7c=0;update_wheel_kinematics(state,pose,input,p,materials,.01f);check(near(state.angle_7c,-.05f)&&near(state.target_angle_80,-.2617994f),"Airborne material rate/global-count fallback wrong");
    const auto saved=state;const auto before_pose=pose;p.remap_material14_to0=false;bool denied=false;try{update_wheel_kinematics(state,pose,input,p,materials,.01f);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(&saved,&state,sizeof(state))==0&&std::memcmp(&before_pose,&pose,sizeof(pose))==0,"Late invalid material partly committed wheel state/pose");
    WheelSpinParameters spin{100,-100,.5f,17};WheelSpinInput drive{0,0,0,0,0,.5f,false,false,0,0,0xffffffffu,0};state.contact_word_34=0;state.spin_rate_1c=100;
    update_wheel_spin(state,drive,spin,.01f);check(near(state.spin_rate_1c,99.5f),"Airborne wheel idle decay wrong");
    state.spin_rate_1c=0;drive.future_tick_13a0=100;update_wheel_spin(state,drive,spin,.01f);check(state.spin_rate_1c==1,"Future unsigned timer did not select native spin target/rate");
    drive.future_tick_13a0=0xffffffffu;state.contact_word_34=1;state.material_40=74;drive.scalar_98=1;drive.speed_parameter=1;update_wheel_spin(state,drive,spin,.01f);check(state.spin_rate_1c==17,"Special material spin override wrong");
    drive.state_word_176c=1;drive.speed_parameter=20;update_wheel_spin(state,drive,spin,.01f);check(state.spin_rate_1c==40,"Raw state-one branch did not select body speed/radius");
    drive.state_word_176c=0;drive.scalar_98=0;drive.speed_parameter=10;state.material_40=0;state.spin_rate_1c=100;update_wheel_spin(state,drive,spin,.01f);check(near(state.spin_rate_1c,96),"Contact no-rate 0.95 relaxation changed");
    const auto prior=state;drive.model_radius_8=0;denied=false;try{update_wheel_spin(state,drive,spin,.01f);}catch(const std::invalid_argument&){denied=true;}check(denied&&std::memcmp(&prior,&state,sizeof(state))==0,"Invalid wheel radius changed spin state");
    std::cout<<"PASS WHEEL_KINEMATICS phase_wrap=true mode2_and3=true mode0_pose_preserved=true material_curves=true spring_force_connection=true spin_timers_and_states=true transactional=true full_tire_model=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

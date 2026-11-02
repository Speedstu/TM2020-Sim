#include "tm2020/recovered_rigid.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b,const char* s){if(!b)throw std::runtime_error(s);}
int main()try{
    RigidWorld world(2);RigidState a,b;a.position={1,2,3};a.linear_velocity={100,-10,25};
    b.linear_velocity={20000,0,0};b.angular_velocity={0,100,0};BodyParameters p{{1,2,3},2};
    world.reset(std::array{a,b},std::array{p,p});world.step(.25f);
    check(world.states()[0].position==std::array{26.f,-.5f,9.25f},"Constant-velocity translation wrong");
    check(world.states()[1].position[0]==5000&&world.states()[1].linear_velocity[0]==10000,"Native clamp order changed");
    check(world.states()[1].angular_velocity[1]==2,"Angular cap wrong");
    auto start=world.snapshot();world.step(.01f);auto finish=world.snapshot();world.restore(start);world.step(.01f);
    check(std::memcmp(world.states().data(),finish.states.data(),sizeof(RigidState)*2)==0,"Snapshot future differs");
    const auto before=world.snapshot();auto invalid=before;invalid.states[1].position[2]=std::numeric_limits<float>::quiet_NaN();
    bool denied=false;try{world.restore(invalid);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&world.tick()==before.tick&&std::memcmp(world.states().data(),before.states.data(),sizeof(RigidState)*2)==0,"Invalid restore partly mutated world");
    denied=false;try{world.step(-.1f);}catch(const std::invalid_argument&){denied=true;}check(denied&&world.tick()==before.tick,"Invalid interval advanced world");
    std::array<float,4> q{};integrate_quaternion(q,{1,2,3},.01f);check(q==std::array{1.f,0.f,0.f,0.f},"Degenerate quaternion fallback wrong");
    std::array<float,9> m{};quaternion_to_matrix(m,q);check(m==std::array{1.f,0.f,0.f,0.f,1.f,0.f,0.f,0.f,1.f},"Identity matrix wrong");
    check(!full_trackmania_physics,"Partial kernel advertised full vehicle physics");
    RigidState falling;BodyParameters body{{0,0,0},100};RigidWorld free(1);free.reset(std::array{falling},std::array{body});
    VelocityStepParameters vp;vp.coefficients={1,1,1,1};vp.model_gravity_scale=1;vp.item_gravity_multiplier=1;
    const GravityEnvironment gravity{{0,-10,0},false,.01f,.9f};std::array<ForceAccumulator,1> forces{};
    free.step_force_then_pose(.25f,forces,std::array{vp},gravity);
    check(free.states()[0].linear_velocity[1]==-2.5f&&free.states()[0].position[1]==-.625f,"Force-to-pose composition wrong");
    check(forces[0].linear==std::array<float,3>{},"Native force clearing lost");
    const auto checkpoint=free.snapshot();
    for(int i=0;i<1000;i++)free.step_force_then_pose(.01f,forces,std::array{vp},gravity);
    const auto future=free.snapshot();free.restore(checkpoint);
    for(int i=0;i<1000;i++)free.step_force_then_pose(.01f,forces,std::array{vp},gravity);
    check(std::memcmp(&future.states[0],&free.states()[0],sizeof(RigidState))==0,"Force trajectory restore differs");
    const auto prior=free.snapshot();forces[0].angular[0]=std::numeric_limits<float>::quiet_NaN();denied=false;
    try{free.step_force_then_pose(.01f,forces,std::array{vp},gravity);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&free.tick()==prior.tick&&std::memcmp(&prior.states[0],&free.states()[0],sizeof(RigidState))==0,"Invalid force partly mutated world");
    auto huge=vp;huge.model_gravity_scale=1e10f;huge.item_gravity_offset=1e10f;huge.item_gravity_multiplier=1e10f;
    huge.coefficients={1e10f,1e10f,1e10f,1e10f};const GravityEnvironment large{{1e10f,1e10f,1e10f},false,.01f,.9f};
    ForceAccumulator accumulator{};RigidState unchanged;const auto original=unchanged;denied=false;
    try{integrate_forces(unchanged,accumulator,huge,large,1);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(&unchanged,&original,sizeof(RigidState))==0,"Overflowing force mutated state");
    std::cout<<"PASS RECOVERED_RIGID autonomous=true reset_restore=true native_clamp_order=true transactional_invalid_restore=true full_vehicle_physics=false\n";
}catch(const std::exception& e){std::cerr<<"RECOVERED_RIGID_ERROR "<<e.what()<<'\n';return 1;}

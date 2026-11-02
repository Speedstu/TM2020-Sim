#include "tm2020/trajectory_hybrid.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::hybrid;
void check(bool pass,const char* message){if(!pass)throw std::runtime_error(message);}
int main()try{
    Tracker t;t.reference.resize(300);t.gains={.1,.1,1.,.1,.001,.05};
    for(unsigned i=0;i<300;++i){auto& r=t.reference[i].data;
        r[0]=r[4]=r[8]=r[12]=1;r[11]=float(i)*.1f;r[18]=10.;r[22]=1;r[24]=.25f;}
    auto state=t.reference[0].data;Cursor cursor;tm2020::internal::Controls c{};std::array<double,12> x{};
    check(t.action(cursor,state.data(),0,c,&x),"Initial inference failed");
    check(c.gas==1&&c.brake==0&&c.steer==32.f/127.f,"Feedforward decode differs");
    t.reference[0].data[22]=0;t.reference[0].data[23]=1;cursor={};
    check(t.action(cursor,state.data(),0,c)&&c.gas==0&&c.brake==1,"Reference pedals ignored");
    t.reference[0].data[22]=1;t.reference[0].data[23]=0;
    state[9]=1.;cursor={};check(t.action(cursor,state.data(),0,c,&x),"Position feedback failed");
    check(c.steer<32.f/127.f,"Position feedback did not correct rightward error");
    state[9]=0.;state[16]=2.;cursor={};check(t.action(cursor,state.data(),0,c),"Velocity feedback failed");
    check(c.steer<32.f/127.f,"Velocity feedback ignored lateral speed");
    cursor={};state=t.reference[0].data;t.network[weights-1]=2.;check(t.action(cursor,state.data(),0,c),"Residual failed");
    check(c.steer>32.f/127.f&&c.steer<=.31f,"Neural residual bound/decode wrong");
    check(!t.action(cursor,state.data(),300,c)&&c.gas==0&&c.brake==0&&c.steer==0,"Clock jump did not neutralize");
    check(!t.action(cursor,state.data(),310,c)&&c.gas==0,"Failed policy silently rearmed");
    cursor={};state[9]=100.;check(!t.action(cursor,state.data(),0,c),"Lost trajectory did not refuse");
    cursor={};state=t.reference[0].data;state[16]=std::numeric_limits<float>::quiet_NaN();
    check(!t.action(cursor,state.data(),0,c),"Nonfinite state accepted");
    state=t.reference[0].data;state[9]=1;state[16]=1;t.network.back()=0;t.reference[0].data[24]=1.;cursor={};
    t.version=1;check(t.action(cursor,state.data(),0,c)&&c.steer<1.,"Legacy saturated-steering behavior changed");
    t.version=2;cursor={};check(t.action(cursor,state.data(),0,c)&&c.steer<1.,"Non-drift saturation bypassed feedback");
    t.reference[0].data[23]=1.;cursor={};check(t.action(cursor,state.data(),0,c)&&c.steer==1.,"Opt-in saturated right steering was unwound");
    t.reference[0].data[24]=-1.;state[9]=-1;state[16]=-1;cursor={};
    check(t.action(cursor,state.data(),0,c)&&c.steer==-1.,"Opt-in saturated left steering was unwound");
    t.version=3;t.feedback_filter={2./127.,0.,20.};t.network={};t.gains={1,0,0,0,.001,0};
    for(auto& r:t.reference){r.data[24]=0.;r.data[22]=1.;r.data[23]=0.;}
    state=t.reference[0].data;state[9]=1./127.;cursor={};
    check(t.action(cursor,state.data(),0,c)&&c.steer==0.,"Feedback deadband ignored");
    state=t.reference[0].data;state[9]=4./127.;cursor={};
    check(t.action(cursor,state.data(),0,c)&&c.steer==-4.f/127.f,"Feedback correction lost");
    state=t.reference[1].data;state[9]=8./127.;
    check(t.action(cursor,state.data(),10,c)&&c.steer==-4.f/127.f,"Feedback hold interval ignored");
    state=t.reference[2].data;state[9]=8./127.;
    check(t.action(cursor,state.data(),20,c)&&c.steer==-8.f/127.f,"Feedback held past interval");
    t.reference[3].data[24]=.5f;t.reference[3].data[22]=0.;t.reference[3].data[23]=1.;state=t.reference[3].data;state[9]=8./127.;
    check(t.action(cursor,state.data(),30,c)&&c.steer==56.f/127.f&&c.gas==0&&c.brake==1,"Filter delayed reference controls");
    cursor={};state=t.reference[0].data;check(t.action(cursor,state.data(),0,c)&&c.steer==0.,"Reset retained feedback");
    t.feedback_filter={0.,2./127.,10.};state[9]=1.;cursor={};
    check(t.action(cursor,state.data(),0,c)&&c.steer==-2.f/127.f,"Feedback slew bound ignored");
    t.version=5;t.human_constraints={10,2,1,0,10,1,20,30,80};
    cursor={};cursor.command_started=true;cursor.previous_steer=0.;cursor.previous_gas=true;
    c={1,0,1};t.constrain(cursor,10,c);
    check(std::abs(c.steer-10.f/127.f)<1e-6,"Human action amplitude/step envelope ignored");
    cursor.previous_steer=c.steer;
    c={1,0,-1};t.constrain(cursor,20,c);
    check(std::abs(c.steer)<1e-6&&cursor.fast_reversal_count==1,"Human rapid reversal budget not recorded");
    cursor.previous_steer=c.steer;
    c={1,0,1};t.constrain(cursor,30,c);
    check(std::abs(c.steer)<1e-6,"Over-budget rapid reversal was emitted");
    cursor.previous_steer=c.steer;cursor.last_gas_change_ms=30;
    c={0,0,0};t.constrain(cursor,40,c);
    check(c.gas==1,"Minimum human gas hold was not enforced");
    c={0,0,0};t.constrain(cursor,50,c);
    check(c.gas==0,"Human gas hold did not release at its allowed duration");
    t.version=6;t.human_envelope={10,100,100,100,10,100,10,10,127,1,1,1,2};
    cursor={};cursor.command_started=true;cursor.previous_steer=0.;cursor.last_steer_change_ms=0;cursor.last_steer_delta=0;
    c={1,0,10.f/127.f};t.constrain(cursor,10,c);check(c.steer==10.f/127.f&&cursor.total_steer_changes==1,"v6 human whole-run steer cap blocked feasible action");
    cursor.previous_steer=c.steer;c={1,0,0};t.constrain(cursor,20,c);check(c.steer==10.f/127.f,"v6 run budget failed to hold steering after cap");
    cursor={};cursor.command_started=true;cursor.previous_gas=true;cursor.last_gas_change_ms=0;
    c={0,0,0};t.constrain(cursor,20,c);check(c.gas==0&&cursor.total_pedal_transitions==1,"v6 pedal transition was not recorded");
    c={1,0,0};t.constrain(cursor,40,c);check(c.gas==0,"v6 total pedal transition budget was not enforced");
    t.version=7;t.contextual_envelope.fill(1.);
    t.contextual_envelope[0]=10;t.contextual_envelope[1]=100;t.contextual_envelope[2]=100;t.contextual_envelope[3]=100;
    t.contextual_envelope[4]=10;t.contextual_envelope[5]=100;t.contextual_envelope[6]=20;t.contextual_envelope[7]=30;t.contextual_envelope[8]=80;
    t.contextual_envelope[9]=1;t.contextual_envelope[13]=1;
    cursor={};cursor.command_started=true;cursor.previous_steer=0.;
    c={1,0,10.f/127.f};t.constrain(cursor,10,c);check(c.steer==10.f/127.f&&cursor.segment_events[0]==1,"v7 local action budget blocked first feasible action");
    cursor.previous_steer=c.steer;c={1,0,0};t.constrain(cursor,20,c);check(c.steer==10.f/127.f,"v7 progress-local budget was not enforced");
    cursor.previous_steer=c.steer;c={1,0,0};t.constrain(cursor,600,c);
    check(cursor.context_segment==1&&cursor.segment_events[0]==1,"v7 local budget did not renew at progress segment");
    t.version=8;t.network={};t.network[513]=10.;t.network[514]=-10.;t.network[512]=.2;
    t.contextual_envelope.fill(100.);t.human_constraints={127,100,100,100,10,100,10,10,127};
    t.gains={0,0,0,0,.001,0};cursor={};state=t.reference[0].data;
    check(t.action(cursor,state.data(),0,c)&&c.gas==1&&c.brake==0,"v8 state-conditioned pedals failed");
    const float first_delta=c.steer;state=t.reference[1].data;
    check(t.action(cursor,state.data(),10,c)&&std::abs(c.steer-std::tanh(.2)-first_delta)<1.f/127.f,
          "v8 steering output is not an increment from the previous applied command");
    t.version=1;t.reference.resize(5000);cursor={4999,49990,true};
    check(!t.budget_expired(cursor,50000)&&t.budget_expired(cursor,50040),"Reference budget boundary differs");
    check(t.action(cursor,state.data(),50040,c)&&c.gas==0&&c.brake==0&&c.steer==0,"End of reference did not neutralize");
    std::cout<<"PASS trajectory feedforward, physical feedback, bounded NN, i8, clock/state/distance failsafes\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

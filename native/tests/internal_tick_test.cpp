#include "tm2020/internal_tick.hpp"
#include "tm2020/internal_input_record.hpp"
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::internal;
static void check(bool x,const char* message){if(!x)throw std::runtime_error(message);}
static bool infer(void* context,const PhysicsTick&,Controls& out)noexcept{
    ++*static_cast<unsigned*>(context);out={1,0,.25f};return true;
}
static PhysicsTick snapshot(){
    PhysicsTick s;s.manager=1;s.vehicle=2;s.body=3;s.interval=.01f;
    s.rigid[0]=s.rigid[4]=s.rigid[8]=s.rigid[12]=1;
    s.session_verified=s.owner_verified=s.race_running=true;return s;
}
int main()try{
    PlayerInputRecord input{};input.bits=2;input.axes={-.5f,1.f,0.f,.25f};input.shorts={123,456};input.buttons=37;
    check(driving_record(input),"Valid original input record rejected");
    const auto command=input_controls(input);check(command.gas==1&&command.brake==0&&command.steer==-.5f,"Input axes order differs");
    check(input_axes(command)==std::array<float,3>{-.5f,1.f,0.f},"Input encoder and decoder differ");
    check(input_record_owner(0x100000,0x1001a8,0x100188,0xa020000,0x200000),"Original player/input binding rejected");
    check(!input_record_owner(0x100000,0x100188,0x1001a8,0xa020000,0x200000),"Swapped history records accepted");
    check(!input_record_owner(0x100000,0x1001a8,0x100188,0xa021000,0x200000),"Another descriptor class accepted");
    input.bits=12;check(!driving_record(input),"Unknown input kind accepted");input.bits=2;
    input.axes[0]=std::numeric_limits<float>::quiet_NaN();check(!driving_record(input),"Nonfinite original axis accepted");
    unsigned calls{};Controller controller;auto s=snapshot();
    CandidateIdentity identity{s.manager,s.vehicle,s.body,100};s.timestamp_ms=200;
    check(qualified_candidate(identity,s,100,false),"same qualified owner rejected");
    s.vehicle++;check(!qualified_candidate(identity,s,100,true),"unexplained new vehicle accepted");
    check(qualified_candidate(identity,s,200,true),"fresh reset with same manager/body rejected");
    check(!qualified_candidate(identity,s,200,false),"reset accepted without authorization");
    s.body++;check(!qualified_candidate(identity,s,200,true),"reset bound another physical body");
    s=snapshot();s.vehicle++;s.timestamp_ms=4000;check(!qualified_candidate(identity,s,200,true),"late owner substitution accepted");
    s=snapshot();s.vehicle++;s.timestamp_ms=200;auto accepted=identity;
    check(commit_qualified_candidate(accepted,s,200,true),"verified reset identity not committed");
    s.timestamp_ms=25000;
    check(qualified_candidate(accepted,s,200,true),"committed reset vehicle expired after three seconds");
    s.vehicle++;
    check(!commit_qualified_candidate(accepted,s,200,true),"late replacement committed after race-start window");
    s=snapshot();s.body++;s.timestamp_ms=200;
    check(!commit_qualified_candidate(accepted,s,300,true),"foreign body committed");
    s=snapshot();
    check(controller.arm(s,infer,&calls),"valid owner did not arm");
    // Owned consumer reads precisely the fields read by original 0x841500.
    std::array<unsigned char,0x1e00> vehicle{};double integrated_drive{};
    for(unsigned tick=0;tick<100;++tick){
        s.timestamp_ms=tick*10;const auto action=controller.before_consume(s);
        std::memcpy(vehicle.data()+0x98,&action,sizeof(action));
        Controls consumed;std::memcpy(&consumed,vehicle.data()+0x98,sizeof(consumed));
        check(consumed.gas==1&&consumed.brake==0&&consumed.steer==32.f/127.f,"consumer saw different controls");
        integrated_drive+=consumed.gas;const auto duplicate=controller.before_consume(s);
        check(duplicate.steer==consumed.steer,"duplicate consumer changed held action");
    }
    check(calls==20&&controller.ticks()==100&&integrated_drive==100,"100 Hz ticks / 20 Hz decisions differ");
    // Actual client splits a 10 ms macro tick into adaptive substeps at speed.
    // A decision must still happen once every five distinct macro timestamps.
    calls=0;s=snapshot();check(controller.arm(s,infer,&calls),"adaptive arm failed");
    for(unsigned tick=0;tick<100;++tick){
        const unsigned count=1+tick%4;s.timestamp_ms=tick*10;s.interval=.01f/count;
        for(unsigned sub=0;sub<count;++sub)check(controller.before_consume(s).gas==1,"adaptive substep neutralized valid input");
    }
    check(calls==20&&controller.ticks()==100,"adaptive calls increased policy frequency");
    calls=0;s=snapshot();check(controller.arm(s,infer,&calls,1),"100 Hz policy arm failed");
    for(unsigned tick=0;tick<100;++tick){
        s.timestamp_ms=tick*10;s.interval=.0025f;
        for(unsigned sub=0;sub<4;++sub)check(controller.before_consume(s).gas==1,"100 Hz substep command failed");
    }
    check(calls==100&&controller.ticks()==100,"100 Hz policy duplicated or skipped a macro tick");
    check(!controller.arm(s,infer,&calls,2),"unsupported policy cadence accepted");
    calls=0;s=snapshot();check(controller.arm(s,infer,&calls),"default cadence restore failed");
    for(unsigned tick=0;tick<100;++tick){s.timestamp_ms=tick*10;controller.before_consume(s);}
    s=snapshot();s.interval=0;check(!valid(s),"zero interval accepted");s.interval=.02f;check(!valid(s),"oversized interval accepted");
    s=snapshot();s.timestamp_ms=990; // Restore the final macro clock for stop.
    s.timestamp_ms+=10;check(controller.before_consume(s,true).gas==0,"stop left throttle active");
    check(controller.fault()==Fault::stopped,"stop reason lost");
    for(int mode=0;mode<5;++mode){
        s=snapshot();check(controller.arm(s,infer,&calls),"rearm failed");controller.before_consume(s);
        s.timestamp_ms=10;
        if(mode==0)s.session_verified=false;
        if(mode==1)s.vehicle++;
        if(mode==2)s.rigid[9]=std::numeric_limits<float>::quiet_NaN();
        if(mode==3)s.timestamp_ms=20;
        if(mode==4)s.race_running=false;
        check(controller.before_consume(s).gas==0&&controller.before_consume(snapshot()).gas==0,"invalid tick did not latch neutral");
    }
    s=snapshot();s.timestamp_ms=2000;
    const std::array<float,3> spawn{s.rigid[9],s.rigid[10],s.rigid[11]};
    const CandidateIdentity prior{s.manager,s.vehicle,s.body,1000};
    check(qualified_restart(prior,s,2000,spawn),"Verified race-zero restart refused");
    s.vehicle++;check(qualified_restart(prior,s,2000,spawn),"Verified replacement vehicle refused");
    s.body++;check(!qualified_restart(prior,s,2000,spawn),"Unverified body rearmed");s.body--;
    s.timestamp_ms=2100;check(!qualified_restart(prior,s,2000,spawn),"Late respawn rearmed");s.timestamp_ms=2000;
    check(!qualified_restart(prior,s,1000,spawn),"Old race rearmed");
    s.rigid[9]+=2;check(!qualified_restart(prior,s,2000,spawn),"Restart away from spawn rearmed");
    std::cout<<"PASS internal tick: macro/adaptive cadence, verified race-zero restart, owner/body/spawn/time guards, stop neutralization\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

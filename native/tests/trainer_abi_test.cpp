#include "tm2020/trainer.h"
#include <array>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
int main(int argc,char** argv)try{
    check(argc==2,"Checkpoint path required");
    tm2020_trainer_handle h{};
    check(tm2020_trainer_create(2,1,16,91,"owned-test-v1",&h)==0,"Create failed");
    const std::array x{.2,-.1};double action{},value{};
    check(tm2020_trainer_observe(h,1,x.data(),2,0,0,1)!=0,"Missing decision accepted");
    check(tm2020_trainer_checkpoint(h,argv[1])==0,"Initial checkpoint failed");
    check(tm2020_trainer_sample(h,x.data(),2,&action,1,&value)==0,"Sample failed");
    const auto first=action;
    check(tm2020_trainer_sample(h,x.data(),2,&action,1,&value)!=0,"Pending overwritten");
    check(tm2020_trainer_checkpoint(h,argv[1])!=0,"Pending checkpoint accepted");
    check(tm2020_trainer_observe(h,std::numeric_limits<double>::quiet_NaN(),x.data(),2,0,0,1)!=0,"NaN reward accepted");
    check(tm2020_trainer_cancel(h)==0,"Cancel failed");
    tm2020_trainer_metrics m{sizeof(m),TM2020_TRAINER_API_VERSION};
    check(tm2020_trainer_update(h,&m)!=0,"Canceled action became transition");
    check(tm2020_trainer_resume(h,argv[1])==0,"Resume failed");
    check(tm2020_trainer_sample(h,x.data(),2,&action,1,&value)==0&&action==first,"Sampler checkpoint changed");
    check(tm2020_trainer_observe(h,1,x.data(),2,0,0,1)==0,"Observe failed");
    check(tm2020_trainer_sample(h,x.data(),2,&action,1,&value)==0,"Second sample failed");
    check(tm2020_trainer_cancel(h)==0,"Failure boundary cancellation failed");
    check(tm2020_trainer_update(h,&m)==0&&m.transitions==1&&m.optimizer_steps>0&&std::isfinite(m.approx_kl),"Accepted prefix update failed");
    check(tm2020_trainer_checkpoint(h,argv[1])==0,"Trained checkpoint failed");
    check(tm2020_trainer_sample(h,x.data(),2,&action,1,&value)==0,"Trained sample failed");
    const auto trained=action;
    check(tm2020_trainer_cancel(h)==0&&tm2020_trainer_resume(h,argv[1])==0,"Trained restore failed");
    check(tm2020_trainer_sample(h,x.data(),2,&action,1,&value)==0&&action==trained,"Training sampler restore changed");
    check(tm2020_trainer_cancel(h)==0,"Final cancel failed");
    tm2020_trainer_close(h);
    check(tm2020_trainer_create(0,1,16,91,"bad",&h)!=0&&h==nullptr,"Invalid architecture accepted");
    std::cout<<"PASS TRAINER_ABI pending_cancel_boundaries_checkpoint_rng=true\n";
}catch(const std::exception& e){std::cerr<<e.what()<<": "<<tm2020_trainer_last_error()<<'\n';return 1;}

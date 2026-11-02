#include "tm2020/read_only_live.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
int main(int argc,char**argv)try {
    if(argc!=2)throw std::invalid_argument("Usage: tm2020_live_consumer_test <live-pose-v3-manifest>");
    tm2020::live::ReadOnlyObserver observer(argv[1]);
    if(observer.process_id()==0||observer.source_count()<4)
        throw std::runtime_error("Invalid native SDK live observer identity");
    unsigned valid=0,hasQ=0;
    for(int i=0;i<100;i++){
        auto candidate=observer.poll();
        if(!candidate)continue;
        if(candidate->authoritative_physics_state_verified||
           candidate->authoritative_100hz_tick_verified||
           candidate->vehicle_owner_verified)
            throw std::runtime_error("Candidate mislabeled authoritative vehicle physics");
        if(!std::isfinite(candidate->xyz.x)||!std::isfinite(candidate->xyz.y)||
           !std::isfinite(candidate->xyz.z)||candidate->position_agreeing_copies<3)
            throw std::runtime_error("Invalid live numeric pose copy quorum");
        valid++;
        if(candidate->raw_quaternion_candidate) {
            hasQ++;
            if(candidate->orientation_agreeing_copies<4)
                throw std::runtime_error("Quaternion candidate did not meet quorum");
        }
    }
    if(valid<90||hasQ<90)throw std::runtime_error("Live pose candidate coverage below 90%");
    std::cout<<"PASS CXX_SDK_LIVE_OBSERVER pid="<<observer.process_id()
             <<" replicas="<<observer.source_count()
             <<" valid="<<valid<<" quaternionCandidate="<<hasQ
             <<" carOwnerProven=false internal100HzProven=false"
             <<" gameMemoryModified=false\n";
    return 0;
}catch(const std::exception& e){
    std::cerr<<"FAIL CXX_LIVE_OBSERVER "<<e.what()<<"\n";return 1;
}

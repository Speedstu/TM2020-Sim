// Native causal XYZ-only velocity observer tests, synthetic + HELDOUT real TM2020.
#include "tm2020.hpp"
#include "tm2020/pose_kinematics.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
static void check(bool condition,const char* message){
    if(!condition)throw std::runtime_error(message);
}
static double norm(tm2020::Vec3 x){
    return std::hypot(x.x,std::hypot(x.y,x.z));
}
static double norm_diff(tm2020::Vec3 a,tm2020::Vec3 b){
    return norm({a.x-b.x,a.y-b.y,a.z-b.z});
}
static double avg(const std::vector<double>& x){
    if(x.empty())throw std::runtime_error("No metrics");
    return std::accumulate(x.begin(),x.end(),0.0)/x.size();
}
int main(int argc,char**argv)try{
    if(argc!=3)throw std::invalid_argument("Usage tm2020_pose_kinematics_test <dataset dir> <CSV report>");
    {
        tm2020::PoseKinematics observer(80.0);
        tm2020::Vec3 start{1000,25,1200},velocity{-25,1.2,12};
        const auto first=observer.observe(0,start);
        check(!first.velocity_observable,"First sample cannot infer velocity");
        for(int i=1;i<=12;i++){
            const double time=i*10.;
            tm2020::Vec3 p{start.x+velocity.x*time/1000.,
                start.y+velocity.y*time/1000.,start.z+velocity.z*time/1000.};
            auto o=observer.observe(time,p);
            check(o.velocity_observable,"Synthetic constant velocity not observable");
            check(norm_diff(o.observed_velocity_ms,velocity)<1e-6,"Wrong synthetic world velocity");
            check(std::abs(o.speed_kmh-3.6*norm(velocity))<1e-6,"Wrong synthetic speed");
        }
        auto teleport=observer.observe(130,{5000,20,1200});
        check(teleport.presumed_teleport&&!teleport.velocity_observable,
            "Teleport should clear finite differences");
        check(observer.samples()==1,"Teleport did not clear history");
        auto gap=observer.observe(1400,{5001,20,1200});
        check(gap.presumed_teleport&&!gap.velocity_observable,"Long gap not rejected");
        auto reverse=observer.observe(1200,{5001,20,1200});
        check(reverse.presumed_teleport&&!reverse.velocity_observable,"Backwards clock not rejected");
        observer.reset();
        check(!observer.observe(2000,{1,2,3}).velocity_observable,"Reset did not clear history");
        std::cout<<"PASS POSE_KINEMATICS_SELFTEST causal 10ms XYZ velocity, reset, teleport, gaps, reversed clocks\n";
    }
    const fs::path folder=argv[1],target=argv[2];
    std::ifstream files(folder/"test.txt");
    check(bool(files),"Expected heldout map split index");
    fs::create_directories(target.parent_path());
    std::ofstream report(target);
    check(bool(report),"Could not write report");
    report<<"map_id,eligible_samples,velocity_vector_mae_ms,speed_mae_kmh,"
             "weighted100ms_speed_mae_kmh,window_length_ms\n";
    std::vector<double> speedErrors,velocityErrors,smoothErrors;
    int ids=0;
    std::string id;
    while(std::getline(files,id)){
        if(id.empty())continue;
        const auto replay=tm2020::Replay::load(folder/(id+".tmreplay"));
        tm2020::PoseKinematics fit(100.0);
        tm2020::PoseKinematics smoothFit(100.0,tm2020::VelocityEstimateMethod::WeightedLeastSquares);
        std::vector<double> err,verr,smoothError;
        tm2020::State previous{};
        bool havePrevious=false;
        for(const auto& sample:replay.states){
            if(sample.time_ms>replay.finish_ms)break;
            auto o=fit.observe(sample.time_ms,sample.position);
            auto w=smoothFit.observe(sample.time_ms,sample.position);
            if(havePrevious && sample.time_ms-previous.time_ms==50 &&
               o.velocity_observable && !o.presumed_teleport){
                const double motion=norm_diff(sample.position,previous.position);
                if(motion<std::max(previous.speed_kmh,sample.speed_kmh)/3.6*.05+6.0 &&
                    sample.speed_kmh<800){
                    const double actualSpeed=sample.speed_kmh;
                    const double speedErr=std::abs(o.speed_kmh-actualSpeed);
                    const double velErr=norm_diff(o.observed_velocity_ms,sample.velocity);
                    const double smoothedSpeed=w.speed_kmh;
                    err.push_back(speedErr);verr.push_back(velErr);
                    smoothError.push_back(std::abs(smoothedSpeed-actualSpeed));
                }
            }
            previous=sample;havePrevious=true;
        }
        check(err.size()>=40,"Too few valid transitions on holdout map");
        ids++;
        speedErrors.insert(speedErrors.end(),err.begin(),err.end());
        velocityErrors.insert(velocityErrors.end(),verr.begin(),verr.end());
        smoothErrors.insert(smoothErrors.end(),smoothError.begin(),smoothError.end());
        report<<id<<","<<err.size()<<","<<avg(verr)<<","<<avg(err)<<","<<avg(smoothError)<<",100\n";
    }
    check(ids==7&&speedErrors.size()>2500,"Heldout map set is not exhaustive");
    const double speed=avg(speedErrors),vel=avg(velocityErrors),smooth=avg(smoothErrors);
    check(std::isfinite(speed)&&std::isfinite(vel)&&
          speed<100&&vel<100,"Heldout observer error out of plausible limits");
    std::cout<<std::fixed<<std::setprecision(4)
        <<"PASS HELDOUT_XYZ_CAUSAL_OBSERVER maps="<<ids
        <<" samples="<<speedErrors.size()
        <<" observerSpeedMAE_KMH="<<speed
        <<" weighted100msSpeedMAE_KMH="<<smooth
        <<" velocityVectorMAE_MS="<<vel
        <<" estimatedFromRecordedXYZ=true"
        <<" actual100HzGameStateValidated=false"
        <<" output="<<target.string()<<"\n";
    return 0;
}catch(const std::exception& e){
    std::cerr<<"FAIL POSE_KINEMATICS "<<e.what()<<"\n";return 1;
}

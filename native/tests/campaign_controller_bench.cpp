#include "tm2020.hpp"
#include "tm2020/route_controller.hpp"
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
struct Scores{double mae{},predictions{},baseline{};int samples{};};
Scores evaluate(const tm2020::RoutePlan& ref,const tm2020::Replay& replay,
                tm2020::PurePursuitConfig conf){
    Scores result;
    for(const auto& s:replay.states) {
        if(s.time_ms>replay.finish_ms)break;
        const auto ctrl=tm2020::propose_reference_controls(ref,s,conf);
        if(!std::isfinite(ctrl.steer)||std::abs(ctrl.steer)>1)
            throw std::runtime_error("Control output invalid");
        result.mae+=std::abs(ctrl.steer-s.controls.steer);
        result.baseline+=std::abs(s.controls.steer);
        result.predictions+=std::abs(ctrl.steer);
        result.samples++;
    }
    if(result.samples<300)throw std::runtime_error("Insufficient heldout controls");
    result.mae/=result.samples;
    result.baseline/=result.samples;
    result.predictions/=result.samples;
    return result;
}
int main(int argc,char**argv)try{
    if(argc!=5)throw std::invalid_argument("Usage tm2020_controller_bench <route_ref> <fit_run> <heldout_run> <csv>");
    auto ref=tm2020::Replay::load(argv[1]);
    auto train=tm2020::Replay::load(argv[2]);
    auto eval=tm2020::Replay::load(argv[3]);
    if(ref.uid!=train.uid||ref.uid!=eval.uid)
        throw std::runtime_error("Route controller cannot cross map UIDs");
    tm2020::RoutePlan planner(ref);
    tm2020::PurePursuitConfig best{};
    Scores trainBest{};
    double bestTrain=1e9;
    unsigned options=0;
    for(double look : {6.,8.,10.,12.,16.,20.,24.,30.,40.,50.}) {
        for(double gain=-12;gain<=12.01;gain+=.5) {
            if(std::abs(gain)<1e-9)continue;
            tm2020::PurePursuitConfig parameters{look,gain};
            const auto score=evaluate(planner,train,parameters);
            ++options;
            if(score.mae<bestTrain){
                bestTrain=score.mae;
                best=parameters;
                trainBest=score;
            }
        }
    }
    const auto val=evaluate(planner,eval,best);
    if(!std::isfinite(val.mae)||val.mae>2.01)
        throw std::runtime_error("Invalid held-out policy metric");
    fs::create_directories(fs::path(argv[4]).parent_path());
    std::ofstream out(argv[4]);
    if(!out)throw std::runtime_error("Cannot write tuning CSV");
    out<<"map_uid,reference_finish_ms,train_finish_ms,eval_finish_ms,"
          "tested_parameter_pairs,lookahead_m,heading_gain,train_steer_mae,"
          "train_zero_steer_mae,heldout_steer_mae,heldout_zero_steer_mae,"
          "heldout_predictions,heldout_beats_baseline,closed_loop_validated\n";
    out<<std::fixed<<std::setprecision(6)
       <<ref.uid<<","<<ref.finish_ms<<","<<train.finish_ms<<","<<eval.finish_ms
       <<","<<options<<","<<best.lookahead_m<<","<<best.heading_gain
       <<","<<trainBest.mae<<","<<trainBest.baseline
       <<","<<val.mae<<","<<val.baseline
       <<","<<val.samples<<","<<(val.mae<val.baseline?"true":"false")<<",false\n";
    std::cout<<"CXX_CAMPAIGN_CONTROLLER fittedLookahead="<<best.lookahead_m
             <<" gain="<<best.heading_gain
             <<" fitSteerMAE="<<trainBest.mae
             <<" evalSteerMAE="<<val.mae
             <<" zeroSteerEvalMAE="<<val.baseline
             <<" beatsBaseline="<<(val.mae<val.baseline)
             <<" closedLoopGameDrivingVerified=false"
             <<" config="<<argv[4]<<"\n";
    return 0;
}catch(const std::exception& e){
    std::cerr<<"FAIL CONTROLLER_BENCH "<<e.what()<<"\n";return 1;
}

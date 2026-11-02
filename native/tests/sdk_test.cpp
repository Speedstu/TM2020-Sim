#include "tm2020.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>

int main(int argc,char** argv){
    try {
        if(argc<3) {std::cerr<<"Usage: tm2020_test <map.tmmap> <replay.tmreplay> [partial.obj]\n";return 2;}
        const auto start=std::chrono::steady_clock::now();
        auto map=tm2020::Map::load(argv[1]);
        auto replay=tm2020::Replay::load(argv[2]);
        const auto ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        tm2020::Dataset data(std::move(map),std::move(replay));
        if(data.replay().states.size()<10||data.map().blocks.empty())throw std::runtime_error("Missing frame or block");
        if(data.replay().sampling_interval_ms!=50)throw std::runtime_error("Unrecognized replay tick");
        if(data.replay().supports_counterfactual_physics_step())throw std::runtime_error("Invalid SDK capability flag");
        const auto& first=data.replay().states.front();
        if(&data.recorded_at(first.time_ms)!=&first)throw std::runtime_error("Recorded state seek mismatch");
        const auto& last=data.replay().states.back();
        if(&data.recorded_at(last.time_ms)!=&last)throw std::runtime_error("End seek mismatch");
        if(data.replay().in_race_transitions()<=0)throw std::runtime_error("Zero race transitions");
        if(data.replay().input_prefix.size()!=data.replay().changes.size())
            throw std::runtime_error("Input prefix does not match event count");
        if(!data.replay().changes.empty()){
            const auto& initial=data.replay().input_at(data.replay().changes[0].time_ms);
            if(initial.steer_raw< -128 ||initial.steer_raw>127)
                throw std::runtime_error("Initial steering outside valid raw input range");
        }
        if(std::abs(tm2020::analog_steer_from_raw(0)-(-1.0/255))>1e-12)
            throw std::runtime_error("Steering conversion mismatch");
        tm2020::RoutePlan route(data.replay());
        if(route.waypoint_count()<10 || route.segment_count()<1)
            throw std::runtime_error("Invalid reference route");
        // Validate observed waypoints can be mapped back to the route.
        std::size_t queries=0;
        double mean_lateral=0;
        const auto valid=data.replay().in_race_transitions();
        for(std::size_t i=0;i<valid;i+=std::max<std::size_t>(valid/80,1)){
            const auto& state=data.replay().states[i];
            auto target=route.target(state.position,state.yaw_rad,20.0);
            if(target.target_sample<target.nearest_sample ||
               target.target_sample>=route.waypoint_count())
                throw std::runtime_error("Reference route lookahead invalid");
            if(target.distance_ahead_m<0 || target.distance_ahead_m>100000)
                throw std::runtime_error("Reference route arc length invalid");
            if(!std::isfinite(target.lateral_error_m))
                throw std::runtime_error("Invalid replay projection error");
            mean_lateral+=target.lateral_error_m;
            ++queries;
            const auto future=route.as_desired_future(state,20.0);
            if(!std::isfinite(future.position.x))
                throw std::runtime_error("Future waypoint invalid");
        }
        // Independent linear oracle validates the 3D KD-tree exact result.
        std::size_t validated_queries=0;
        for(std::size_t ix=0;ix<valid;ix+=std::max<std::size_t>(valid/30,1)){
            const auto& s=data.replay().states[ix];
            tm2020::Vec3 q{s.position.x+7.5,s.position.y+1.2,s.position.z-3.5};
            const double heading=s.yaw_rad+0.13;
            double best=std::numeric_limits<double>::infinity();
            std::size_t winner=0;
            for(std::size_t j=0;j<route.waypoint_count();j++){
                const auto& w=data.replay().states[j];
                const double dx=q.x-w.position.x,dy=q.y-w.position.y,dz=q.z-w.position.z;
                const double d=dx*dx+dy*dy+dz*dz;
                const double a=std::remainder(w.yaw_rad-heading,6.2831853071795864769);
                const double score=d+25*(1-std::cos(a));
                if(score<best){best=score;winner=j;}
            }
            const auto actual=route.target(q,heading,25.0);
            if(actual.nearest_sample!=winner)
                throw std::runtime_error("3D KD route query disagrees with independent linear search");
            ++validated_queries;
        }
        if(validated_queries<10)throw std::runtime_error("Not enough KD comparisons");
        std::cout<<"[ROUTE] waypoints="<<route.waypoint_count()
                 <<" segments="<<route.segment_count()
                 <<" queries="<<queries
                 <<" meanRecordedLateralError="<<mean_lateral/queries<<"\n";
        if(argc>=4){
            tm2020::CollisionWorld world(argv[3]);
            if(world.triangle_count()==0)throw std::runtime_error("Empty collision mesh");
            double rays[14]={
                first.position.x,first.position.y+2,first.position.z,0,-1,0,8,
                last.position.x,last.position.y+2,last.position.z,0,-1,0,8
            };
            double out[18];
            world.raycast(rays,2,out);
            std::cout<<"[COLLIDER] partial-tris="<<world.triangle_count()
                <<" first-ray-hit="<<out[0]<<" last-ray-hit="<<out[9]<<"\n";
        }
        if(argc>=5){
            const auto policy=tm2020::BCPolicy::load(argv[4]);
            if(data.replay().states.size()>6){
                const auto predicted=policy.predict(data.replay().states[0],data.replay().states[5]);
                if(!std::isfinite(predicted.steer) || predicted.steer<-1.001 || predicted.steer>1.001)
                    throw std::runtime_error("Native BC inference out of range");
                std::cout<<"[POLICY] steer="<<predicted.steer<<" gas="<<predicted.gas
                         <<" brake="<<predicted.brake<<" (oracle-future waypoint)"<<"\n";
            }
        }
        std::cout<<"[PASS] uid="<<data.map().uid
                 <<" map-blocks="<<data.map().blocks.size()
                 <<" items="<<data.map().items.size()
                 <<" replay-frames="<<data.replay().states.size()
                 <<" input-events="<<data.replay().changes.size()
                 <<" valid-transitions="<<data.replay().in_race_transitions()
                 <<" load-ms="<<std::fixed<<std::setprecision(2)<<ms
                 <<" full-physics=false\n";
        return 0;
    }catch(const std::exception& e){
        std::cerr<<"[FAIL] "<<e.what()<<"\n";
        return 1;
    }
}

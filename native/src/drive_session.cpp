// Real-time local Solo reference follower. VISUAL telemetry; no exact step().
#include "tm2020/read_only_live.hpp"
#include "tm2020/local_input.hpp"
#include "tm2020/route_controller.hpp"
#include "tm2020/actuator.hpp"
#include "tm2020/driving_features.hpp"
#include "tm2020/realtime_rollout.hpp"
#include "drive_session.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <chrono>
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <thread>
int tm2020::live::run_drive_cli(int argc,char** argv)try{
    if(argc<10||std::string(argv[1])!="--confirm-local-solo")throw std::invalid_argument(
        "Usage: tm2020_live_drive --confirm-local-solo pose-manifest replay output.csv keyboard|gamepad dll seconds lookahead gain [--feedforward|--tracking|--replay-clock] [--deadzone value] [--ppo-update model|--ppo-evaluate model]");
    bool feedforward=false,tracking=false,replay_clock=false;std::optional<double> deadzone;
    std::optional<std::filesystem::path> learning_model;
    bool evaluate=false;
    for(int i=10;i<argc;i++){
        const std::string option=argv[i];
        if(option=="--deadzone"&&i+1<argc){deadzone=std::stod(argv[++i]);(void)tm2020::live::inverse_steering_deadzone(0,*deadzone);}
        else if(option=="--feedforward")feedforward=true;
        else if(option=="--tracking")tracking=true;
        else if(option=="--replay-clock")replay_clock=true;
        else if((option=="--ppo-update"||option=="--ppo-evaluate")&&i+1<argc){
            if(learning_model)throw std::invalid_argument("Choose one PPO update/evaluation model");
            evaluate=option=="--ppo-evaluate";learning_model=std::filesystem::absolute(argv[++i]);
        }
        else throw std::invalid_argument("Unknown/incomplete controller option");
    }
    if(int(feedforward)+int(tracking)+int(replay_clock)>1)throw std::invalid_argument("Choose one controller mode");
    const auto replay=tm2020::Replay::load(argv[3]);const tm2020::RoutePlan route(replay);
    const std::string learning_schema=std::string(tm2020::driving_observation_schema)+"|tracking_residual_scale=.2_period_ms=100|map="+replay.uid;
    std::optional<tm2020::rl::ActorCritic> learning_policy;
    std::unique_ptr<tm2020::rl::RealtimeResidualRollout> rollout;
    std::unique_ptr<tm2020::rl::RealtimeResidualEvaluation> evaluation;
    std::unique_ptr<tm2020::rl::PpoTrainer> trainer;
    bool adam_restored=false;
    std::filesystem::path training_checkpoint;
    if(learning_model){
        if(!tracking)throw std::invalid_argument("Real-time residual PPO requires --tracking");
        training_checkpoint=*learning_model;training_checkpoint+=".train";
        const bool resume=!evaluate&&std::filesystem::exists(training_checkpoint);
        if(!resume&&std::filesystem::exists(*learning_model)){
            std::string schema;learning_policy=tm2020::rl::ActorCritic::load(*learning_model,&schema);
            if(schema!=learning_schema||learning_policy->actor.inputs!=8||learning_policy->actor.outputs!=1)
                throw std::invalid_argument("Residual model observation/action schema mismatch");
        }else{
            if(evaluate)throw std::invalid_argument("Evaluation requires an existing inference model");
            learning_policy.emplace(8,1,32,2026);
            auto& actor=learning_policy->actor;
            std::fill(actor.parameters.begin()+actor.hidden*(actor.inputs+1),actor.parameters.end(),0.);
            learning_policy->log_std[0]=-2.;
        }
        if(evaluate)evaluation=std::make_unique<tm2020::rl::RealtimeResidualEvaluation>(*learning_policy);
        else {
            tm2020::rl::PpoConfig config;config.learning_rate=1e-4;config.epochs=4;config.clip=.1;config.target_kl=.01;
            trainer=std::make_unique<tm2020::rl::PpoTrainer>(*learning_policy,config,2026);
            std::mt19937_64 sampler(2026);
            if(resume){trainer->load_checkpoint(training_checkpoint,learning_schema,sampler);adam_restored=true;}
            std::filesystem::create_directories(learning_model->parent_path());
            learning_policy->save(std::string(argv[4])+".behavior.tmppo",learning_schema);
            rollout=std::make_unique<tm2020::rl::RealtimeResidualRollout>(*learning_policy,sampler);
        }
    }
    const double seconds=std::stod(argv[7]),lookahead=std::stod(argv[8]),gain=std::stod(argv[9]);
    if(!std::isfinite(seconds)||seconds<1||seconds>120||lookahead<2||lookahead>200||!std::isfinite(gain)||std::abs(gain)>100)
        throw std::invalid_argument("Invalid run limits");
    const std::string backend=argv[5];if(backend!="keyboard"&&backend!="gamepad")throw std::invalid_argument("Unknown backend");
    tm2020::live::ReadOnlyObserver observer(argv[2],2.);
    auto poll=[&]()->std::optional<tm2020::live::FreshVisualSample>{
        return observer.poll_fresh_visual(std::nullopt,true);
    };
    tm2020::live::LocalInput input(observer.process_id(),backend=="keyboard"?tm2020::live::InputBackend::Keyboard:tm2020::live::InputBackend::ViGEmXbox360,std::filesystem::absolute(argv[6]));
    std::ofstream out(argv[4]);if(!out)throw std::runtime_error("Cannot write trace");
    out<<"wall_s,clock_candidate_ms,x,y,z,vx,vy,vz,heading_used_rad,front_speed,command_steer,gas,reference_error_m,nearest_sample,quorum,matrix_column_yaw,matrix_row_yaw,velocity_yaw,heading_column_votes,heading_row_votes,measured_steer,measured_gas,measured_brake,race_start_ms,race_ms,ground,reference_yaw,reference_speed_kmh,reference_steer,command_brake,actuator_steer,host_pid,recovery_count,policy_residual\n";
    input.start_race();std::this_thread::sleep_for(std::chrono::milliseconds(400));
    input.restart();std::this_thread::sleep_for(std::chrono::milliseconds(600));
    const auto cache=std::filesystem::path(std::string(argv[2])+".visual-cache");
    bool cached=observer.restore_visual_sources(cache);
    auto cached_state=cached?poll():std::nullopt;
    if(cached&&!cached_state)cached=false;
    if(cached_state&&std::hypot(cached_state->state.position.x-replay.states.front().position.x,
        cached_state->state.position.z-replay.states.front().position.z)>8)cached=false;
    if(!cached){
        std::cout<<"REACQUIRED_REFLECTED_VISUAL_PAGES="<<observer.discover_visual_states(8192,2.,replay.states.front().position)<<std::endl;
        observer.save_visual_sources(cache);
    }else std::cout<<"LIVE_VISUAL_CACHE_REVALIDATED=true"<<std::endl;
    // Scanning must never become part of the lap time. This is a normal game
    // restart after discovery/revalidation, for every controller mode.
    const auto before_reset=poll();
    input.restart();
    using Clock=std::chrono::steady_clock;
    const auto reset_deadline=Clock::now()+std::chrono::seconds(8);
    std::optional<tm2020::live::FreshVisualSample> first,previous_reset_sample;
    const auto& start_state=replay.states.front();
    // Device hotplug and a normal reset can stall rendering beyond 600 ms.
    // Keep controls neutral until a NEW episode and an advancing clock agree.
    while(Clock::now()<reset_deadline){
        auto candidate=poll();
        if(candidate&&candidate->state.race_start_time!=-1&&
           (!before_reset||before_reset->state.race_start_time==-1||
            candidate->state.race_start_time!=before_reset->state.race_start_time)&&
           std::hypot(candidate->state.position.x-start_state.position.x,candidate->state.position.z-start_state.position.z)<=8){
            if(previous_reset_sample&&previous_reset_sample->state.race_start_time==candidate->state.race_start_time&&
               static_cast<std::int32_t>(candidate->clock_candidate_ms-previous_reset_sample->clock_candidate_ms)>0){first=candidate;break;}
            previous_reset_sample=candidate;
        }else previous_reset_sample.reset();
        std::this_thread::sleep_for(std::chrono::milliseconds(30));
    }
    if(!first)throw std::runtime_error("Normal restart not verified: need new active episode, start pose and advancing visual clock within 8s");
    const auto start=Clock::now();auto last_valid=start,last_advance=start;
    std::uint32_t last_clock=first->clock_candidate_ms;double yaw=start_state.yaw_rad,max_progress=0,max_error=0;
    std::size_t rows{},drops{},recoveries{};bool endpoint=false;
    auto last_motion=start,recovery_until=start;
    std::size_t column_votes=0,row_votes=0;
    std::string loop_error;
    try{
    for(std::size_t tick=0;;tick++){
        const auto now=Clock::now();const auto elapsed=std::chrono::duration<double>(now-start).count();if(elapsed>=seconds)break;
        const auto sample=poll();
        if(!sample){input.neutral();drops++;if(now-last_valid>std::chrono::milliseconds(250))throw std::runtime_error("Visual quorum lost >250ms");}
        else {
            if(sample->state.race_start_time!=first->state.race_start_time)
                throw std::runtime_error("Visual episode changed during driving; valid PPO prefix truncated");
            last_valid=now;if(sample->clock_candidate_ms!=last_clock){last_clock=sample->clock_candidate_ms;last_advance=now;}
            if(now-last_advance>std::chrono::milliseconds(500))throw std::runtime_error("Visual clock stopped >500ms");
            const auto& v=sample->state;tm2020::State state{};state.position=v.position;state.velocity=v.world_velocity;
            const double speed=std::hypot(v.world_velocity.x,v.world_velocity.z);
            const double velocity_yaw=std::atan2(v.world_velocity.x,v.world_velocity.z);
            const auto& matrix=v.location_rotation_matrix;
            const double column_yaw=std::atan2(matrix[2],matrix[8]),row_yaw=std::atan2(matrix[6],matrix[8]);
            auto difference=[](double a,double b){return std::abs(std::remainder(a-b,6.283185307179586));};
            if(v.rotation_matrix_is_orthonormal&&v.ground_contact&&speed>10&&difference(column_yaw,row_yaw)>.15&&column_votes+row_votes<100){
                if(difference(column_yaw,velocity_yaw)<difference(row_yaw,velocity_yaw))column_votes++;else row_votes++;
            }
            if(v.rotation_matrix_is_orthonormal&&column_votes+row_votes>=5)
                yaw=column_votes>row_votes?column_yaw:row_yaw;
            else if(speed>2)yaw=velocity_yaw;
            state.yaw_rad=yaw;state.speed_kmh=speed*3.6;
            const auto target=route.target(state.position,yaw,lookahead);
            max_progress=std::max(max_progress,double(target.nearest_sample)/double(route.waypoint_count()-1));
            max_error=std::max(max_error,target.lateral_error_m);
            if(target.lateral_error_m>35)throw std::runtime_error("Car left reference corridor >35m");
            auto action=tm2020::propose_reference_controls(route,state,{lookahead,gain});
            if(feedforward){
                const auto& reference_state=replay.states.at(target.nearest_sample);
                const double heading_error=std::remainder(reference_state.yaw_rad-yaw,6.283185307179586);
                const double dx=reference_state.position.x-state.position.x,dz=reference_state.position.z-state.position.z;
                const double lateral=std::cos(yaw)*dx-std::sin(yaw)*dz;
                action.steer=std::clamp(reference_state.controls.steer+gain*heading_error-.03*lateral,-1.,1.);
                action.brake=reference_state.controls.brake;
                action.gas=reference_state.controls.gas;
                // A positional policy otherwise waits forever at sample zero,
                // whose replay inputs can precede the initial throttle press.
                if(max_progress<.05&&speed<1){action.gas=1;action.brake=0;}
                if(state.speed_kmh>reference_state.speed_kmh+25){action.gas=0;action.brake=1;}
            }
            if(tracking)action=tm2020::propose_tracking_controls(replay,route,state,{gain,.15,2,true});
            if(replay_clock){
                const auto race_ms=static_cast<std::int32_t>(sample->clock_candidate_ms-static_cast<std::uint32_t>(v.race_start_time));
                if(race_ms>replay.finish_ms+1000)break;
                if(race_ms<0)action={0,1,0};
                else {
                    const auto recorded=replay.input_at(race_ms);
                    action={tm2020::live_steer_from_raw(recorded.steer_raw),recorded.gas?1.:0.,recorded.brake?1.:0.};
                }
            }
            if(speed>2||max_progress<.1)last_motion=now;
            if(tracking&&now>=recovery_until&&now-last_motion>std::chrono::milliseconds(1400)){
                if(recoveries>=4)throw std::runtime_error("Stuck after four bounded reverse recoveries");
                recoveries++;recovery_until=now+std::chrono::milliseconds(1200);last_motion=recovery_until;
            }
            if(now<recovery_until){
                const double error=std::remainder(replay.states.at(target.nearest_sample).yaw_rad-yaw,6.283185307179586);
                action={-std::clamp(gain*error,-1.,1.),0,1};
            }
            double correction=0;
            if(rollout||evaluation){
                state.ground_contact=v.ground_contact;
                const auto features=tm2020::driving_features(route,state);
                correction=rollout?rollout->observe(features,sample->clock_candidate_ms,
                    double(target.nearest_sample),target.lateral_error_m):evaluation->observe(features,sample->clock_candidate_ms);
                action.steer=std::clamp(action.steer+correction,-1.,1.);
            }
            auto actuator=action;
            if(deadzone)actuator.steer=tm2020::live::inverse_steering_deadzone(action.steer,*deadzone);
            input.apply(actuator);
            out<<std::setprecision(9)<<elapsed<<','<<sample->clock_candidate_ms<<','<<v.position.x<<','<<v.position.y<<','<<v.position.z
               <<','<<v.world_velocity.x<<','<<v.world_velocity.y<<','<<v.world_velocity.z<<','<<yaw<<','<<v.front_speed
               <<','<<action.steer<<','<<action.gas<<','<<target.lateral_error_m<<','<<target.nearest_sample<<','<<sample->agreeing_copies
               <<','<<column_yaw<<','<<row_yaw<<','<<velocity_yaw<<','<<column_votes<<','<<row_votes
               <<','<<v.input_steer<<','<<v.input_gas<<','<<v.input_brake<<','<<v.race_start_time
               <<','<<static_cast<std::int32_t>(sample->clock_candidate_ms-static_cast<std::uint32_t>(v.race_start_time))
               <<','<<v.ground_contact<<','<<replay.states.at(target.nearest_sample).yaw_rad
               <<','<<replay.states.at(target.nearest_sample).speed_kmh<<','<<replay.states.at(target.nearest_sample).controls.steer
               <<','<<action.brake<<','<<actuator.steer<<','<<GetCurrentProcessId()<<','<<recoveries<<','<<correction<<'\n';rows++;
            const auto& end_state=replay.states.at(route.waypoint_count()-1);
            const double past_end=(v.position.x-end_state.position.x)*std::sin(end_state.yaw_rad)+
                                  (v.position.z-end_state.position.z)*std::cos(end_state.yaw_rad);
            // A lookahead reaching the last node is not a finish: that used to
            // release throttle tens of metres before the final ramp/gates.
            if(target.nearest_sample+2>=route.waypoint_count()&&past_end>5&&target.lateral_error_m<20){endpoint=true;break;}
        }
        std::this_thread::sleep_until(start+std::chrono::milliseconds((tick+1)*10));
    }
    }catch(const std::exception& error){loop_error=error.what();}
    input.neutral();
    if(rollout){
        rollout->truncate();rollout->write_csv(std::string(argv[4])+".rollout.csv");
        const auto& transitions=rollout->transitions();
        if(transitions.size()>=32){
            const auto before=learning_policy->actor.parameters;
            const auto metrics=trainer->update(transitions,1);
            double change=0;for(std::size_t i=0;i<before.size();i++)change+=std::pow(before[i]-learning_policy->actor.parameters[i],2);
            // The self-contained training checkpoint is authoritative. If the
            // process stops before inference export, the next update resumes it.
            trainer->save_checkpoint(training_checkpoint,learning_schema,rollout->sampling_rng());
            const auto temporary=learning_model->wstring()+L".tmp";
            learning_policy->save(std::filesystem::path(temporary),learning_schema);
            if(!MoveFileExW(temporary.c_str(),learning_model->c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))
                throw std::runtime_error("Atomic PPO model update failed; temporary checkpoint retained");
            std::ofstream metrics_out(std::string(argv[4])+".ppo.csv");
            metrics_out<<"transitions,minibatches,epochs,approx_kl,actor_parameter_l2_change,on_policy_identity_checked,all_completed_prefixes_truncated,adam_state_restored,session_had_error,game_strength_improvement_verified\n"
                <<transitions.size()<<','<<metrics.minibatches<<','<<metrics.epochs<<','<<metrics.approx_kl<<','<<std::sqrt(change)
                <<",true,true,"<<adam_restored<<','<<!loop_error.empty()<<",false\n";
            metrics_out.flush();if(!metrics_out)throw std::runtime_error("Cannot export PPO update metrics");
        }
    }
    if(evaluation){
        std::ofstream metrics_out(std::string(argv[4])+".evaluation.csv");
        metrics_out<<"deterministic,no_exploration,optimizer_updates,trace_rows,reference_endpoint,session_had_error,game_finish_verified\n"
                   <<"true,true,0,"<<rows<<','<<endpoint<<','<<!loop_error.empty()<<",false\n";
        metrics_out.flush();if(!metrics_out)throw std::runtime_error("Cannot export evaluation metrics");
    }
    if(!loop_error.empty())throw std::runtime_error(loop_error);
    std::cout<<"REAL_LOCAL_FOLLOWER rows="<<rows<<" dropped="<<drops<<" max_reference_progress="<<max_progress
             <<" max_reference_error_m="<<max_error<<" reached_reference_endpoint="<<endpoint
             <<" recoveries="<<recoveries<<" host_pid="<<GetCurrentProcessId()
             <<" column_heading_votes="<<column_votes<<" row_heading_votes="<<row_votes<<" game_finish_counter_verified=false\n";
    return 0;
}catch(const std::exception& e){
    std::cerr<<"LIVE_DRIVE_ERROR "<<e.what()<<'\n';
    if(argc>4)try{std::ofstream error(std::string(argv[4])+".error.txt");error<<e.what()<<'\n';}catch(...){}
    return 1;
}

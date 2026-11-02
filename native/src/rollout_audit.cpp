// Independently re-evaluate every retained behavior likelihood and value.
#include "tm2020/rl.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
std::vector<std::string> split(const std::string& line){
    std::vector<std::string> fields;std::istringstream in(line);std::string cell;
    while(std::getline(in,cell,','))fields.push_back(cell);return fields;
}
double number(const std::string& text){
    std::size_t end{};const double x=std::stod(text,&end);
    if(end!=text.size()||!std::isfinite(x))throw std::invalid_argument("Invalid numeric rollout field");return x;
}
int main(int argc,char** argv)try{
    const bool multiple=argc==5&&std::string(argv[4])=="--multiple-episodes";
    if(argc!=4&&!multiple)throw std::invalid_argument("Usage: tm2020_rollout_audit behavior.tmppo rollout.csv output.json [--multiple-episodes]");
    const auto policy=tm2020::rl::ActorCritic::load(argv[1]);
    if(!multiple&&policy.actor.outputs!=1)throw std::invalid_argument("Legacy audit requires one residual action");
    std::ifstream in(argv[2]);std::string line;
    if(!std::getline(in,line))throw std::runtime_error("Cannot read rollout CSV");
    auto header=split(line);std::vector<std::string> expected{"old_log_probability","old_value","reward","next_value","terminated","truncated","elapsed_steps"};
    if(multiple){for(std::size_t j=0;j<policy.actor.outputs;j++)expected.push_back("latent_"+std::to_string(j));}
    else expected.push_back("latent");
    for(std::size_t j=0;j<policy.actor.inputs;j++)expected.push_back("observation_"+std::to_string(j));
    if(header!=expected)throw std::invalid_argument("Rollout CSV schema mismatch");
    std::vector<tm2020::rl::Transition> rows;double log_error=0,value_error=0;std::size_t boundaries=0;
    while(std::getline(in,line)){
        if(rows.size()>=1000000)throw std::invalid_argument("Rollout too large");
        const auto fields=split(line);if(fields.size()!=expected.size())throw std::invalid_argument("Malformed rollout row");
        std::vector<double> v;for(const auto& f:fields)v.push_back(number(f));
        if((v[4]!=0&&(!multiple||v[4]!=1))||(v[5]!=0&&v[5]!=1))throw std::invalid_argument("Unexpected termination/truncation label");
        const auto action_end=7+policy.actor.outputs;
        tm2020::rl::Transition t{{v.begin()+action_end,v.end()},{v.begin()+7,v.begin()+action_end},v[0],v[1],v[2],v[3],v[4]==1,v[5]==1,v[6]};
        boundaries+=t.terminated||t.truncated;
        log_error=std::max(log_error,std::abs(policy.log_probability(t.observation,t.latent)-t.old_log_probability));
        value_error=std::max(value_error,std::abs(policy.value(t.observation)-t.old_value));
        rows.push_back(std::move(t));
    }
    if(!in.eof()||rows.empty()||!(rows.back().truncated||(multiple&&rows.back().terminated))||
       (!multiple&&std::any_of(rows.begin(),rows.end()-1,[](const auto& t){return t.truncated;}))||log_error>1e-7||value_error>1e-7)
        throw std::invalid_argument("Retained rollout failed behavior identity/boundary audit");
    (void)tm2020::rl::generalized_advantage(rows,1);
    std::ofstream out(argv[3]);out<<std::setprecision(17)
        <<"{\"schema\":\""<<(multiple?"tm2020_behavior_rollout_audit_v2":"tm2020_behavior_rollout_audit_v1")<<"\",\"transitions\":"<<rows.size()
        <<",\"action_count\":"<<policy.actor.outputs<<",\"episode_boundaries\":"<<boundaries
        <<",\"max_log_probability_error\":"<<log_error<<",\"max_value_error\":"<<value_error
        <<",\"all_rows_recomputed\":true,\"final_prefix_truncated\":"<<(rows.back().truncated?"true":"false")<<",\"policy_mutated\":false}\n";
    out.flush();if(!out)throw std::runtime_error("Cannot write audit report");
    std::cout<<"PASS BEHAVIOR_AUDIT transitions="<<rows.size()<<" max_logp_error="<<log_error<<" max_value_error="<<value_error<<'\n';
}catch(const std::exception& e){std::cerr<<"ROLLOUT_AUDIT_ERROR "<<e.what()<<'\n';return 1;}

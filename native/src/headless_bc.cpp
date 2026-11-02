// Supervised initialization on engine observations aligned with recorded controls.
// Validation and test must be whole separate replay files, never shuffled row splits.
#include "tm2020/rl.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <stdexcept>

constexpr std::size_t nx=233,na=3;
constexpr const char* schema="tm2020_gearbox_geometry233_v1|actions=unit_pedals_steering3_v1";
struct Example{std::array<double,nx> x;std::array<double,na> y;};
std::vector<Example> load(const std::filesystem::path& path){
    std::ifstream in(path);if(!in)throw std::runtime_error("Cannot open BC dataset");
    std::string line;std::getline(in,line);std::string header;
    for(std::size_t i=0;i<nx;i++)header+="observation_"+std::to_string(i)+",";
    header+="gas,brake,steer,race_ms";
    if(line!=header)throw std::runtime_error("Unknown BC CSV header");
    std::vector<Example> rows;
    while(std::getline(in,line)){
        if(line.empty())continue;
        std::stringstream stream(line);std::string word;std::vector<double> values;
        while(std::getline(stream,word,',')){
            std::size_t end=0;const auto value=std::stod(word,&end);
            if(end!=word.size()||!std::isfinite(value))throw std::runtime_error("Invalid BC value");
            values.push_back(value);
        }
        if(values.size()!=nx+4)throw std::runtime_error("Invalid BC row shape");
        Example row;std::copy_n(values.begin(),nx,row.x.begin());
        if(values[nx]<0||values[nx]>1||values[nx+1]<0||values[nx+1]>1||std::abs(values[nx+2])>1)
            throw std::runtime_error("Invalid BC controls");
        row.y={2*values[nx]-1,2*values[nx+1]-1,values[nx+2]};rows.push_back(row);
        if(rows.size()>1000000)throw std::runtime_error("BC row bound");
    }
    if(rows.size()<100)throw std::runtime_error("Insufficient BC examples");return rows;
}
double loss(const tm2020::rl::ActorCritic& policy,const std::vector<Example>& rows){
    double sum=0;for(const auto& row:rows){const auto action=policy.deterministic(row.x).action;
        for(std::size_t i=0;i<na;i++)sum+=std::pow(action[i]-row.y[i],2);}
    return sum/(na*rows.size());
}
int main(int argc,char**argv)try{
    if(argc!=6)throw std::invalid_argument("headless_bc fit.csv validation.csv test.csv output_dir epochs");
    for(int i=1;i<4;i++)for(int j=i+1;j<4;j++)if(std::filesystem::equivalent(argv[i],argv[j]))
        throw std::invalid_argument("BC requires independent replay files");
    const auto epochs=std::stoul(argv[5]);if(!epochs||epochs>1000)throw std::invalid_argument("Epoch bound");
    const std::filesystem::path output(argv[4]);if(std::filesystem::exists(output))throw std::runtime_error("Never overwrite BC run");
    std::filesystem::create_directories(output);
    const auto fit=load(argv[1]),validation=load(argv[2]);
    tm2020::rl::ActorCritic policy(nx,na,128,2026),best=policy;
    auto& weights=policy.actor.parameters;const auto base=policy.actor.hidden*(nx+1);
    std::fill(weights.begin()+base,weights.end(),0.0);weights[base+na*policy.actor.hidden]=3;
    weights[base+na*policy.actor.hidden+1]=-3;policy.log_std={-3,-3,-4};best=policy;
    std::vector<double> m(weights.size()),v(weights.size());std::vector<std::size_t> order(fit.size());
    std::iota(order.begin(),order.end(),0);std::mt19937_64 rng(2026);std::size_t updates=0,best_epoch=0;
    double best_loss=loss(policy,validation);const auto initial=best_loss;
    for(std::size_t epoch=0;epoch<epochs;epoch++){
        std::shuffle(order.begin(),order.end(),rng);
        for(std::size_t begin=0;begin<order.size();begin+=64){
            const auto end=std::min(order.size(),begin+64);std::vector<double> gradient(weights.size());
            for(std::size_t at=begin;at<end;at++){
                const auto& row=fit[order[at]];const auto predicted=policy.actor.forward(row.x);std::array<double,na> upstream;
                for(std::size_t i=0;i<na;i++){const auto y=std::tanh(predicted[i]);
                    upstream[i]=(y-row.y[i])*(1-y*y)/(na*double(end-begin));}
                policy.actor.backward(row.x,upstream,gradient);
            }
            updates++;const auto b1=1-std::pow(.9,double(updates)),b2=1-std::pow(.999,double(updates));
            for(std::size_t k=0;k<weights.size();k++){
                const auto g=gradient[k];m[k]=.9*m[k]+.1*g;v[k]=.999*v[k]+.001*g*g;
                weights[k]-=.001*(m[k]/b1)/(std::sqrt(v[k]/b2)+1e-8);
            }
        }
        const auto current=loss(policy,validation);if(current<best_loss){best_loss=current;best_epoch=epoch+1;best=policy;}
    }
    // Test labels are read only after validation has selected the epoch.
    const auto test=load(argv[3]);const auto heldout=loss(best,test);
    best.save(output/"policy.tmppo",schema);
    tm2020::rl::PpoTrainer trainer(best,{},2026);std::mt19937_64 sampler(2026);
    trainer.save_checkpoint(output/"training.checkpoint",schema,sampler);
    std::ofstream report(output/"report.json");report<<std::setprecision(17)
        <<"{\"schema\":\"tm2020_headless_bc_v1\",\"fitRows\":"<<fit.size()<<",\"validationRows\":"<<validation.size()
        <<",\"testRows\":"<<test.size()<<",\"epochs\":"<<epochs<<",\"selectedEpoch\":"<<best_epoch
        <<",\"initialValidationMse\":"<<initial<<",\"selectedValidationMse\":"<<best_loss<<",\"testMse\":"<<heldout
        <<",\"testUsedForSelection\":false,\"learnedActor\":true,\"ppoOptimizerSteps\":0,\"generalPolicyQualified\":false,\"raceStrengthQualified\":false}\n";
    if(!report)throw std::runtime_error("Cannot write BC report");
    std::cout<<"HEADLESS_BC epoch="<<best_epoch<<" validation_mse="<<best_loss<<" heldout_mse="<<heldout<<'\n';
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}

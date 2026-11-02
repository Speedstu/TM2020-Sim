// Trackmania 2020 native C++20 offline behavior cloning (BC) baseline.
// Uses observed replay car states and an ORACLE 250ms future waypoint. This is
// supervised imitation / policy research, NOT RL and NOT a physics simulator.
// Only scores map-held-out data and compares no-steer/gas-always/brake-never.
#include "tm2020.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs=std::filesystem;
constexpr int F=24;
using Features=tm2020::BCFeatures;
using Targets=std::array<double,3>;

struct Sample {Features x{};Targets y{};};
struct DataSet {std::vector<Sample> samples;std::size_t maps=0;};
constexpr double kPi=3.14159265358979323846;

static double wrap(double x){
    return std::remainder(x,2*kPi);
}
static DataSet load(const fs::path& folder,const std::string& split) {
    std::ifstream file(folder/(split+".txt"));
    if(!file)throw std::runtime_error("Missing split index: "+split);
    DataSet result;
    std::string line;
    while(std::getline(file,line)){
        if(line.empty())continue;
        if(line.find_first_not_of("0123456789")!=std::string::npos)
            throw std::runtime_error("Bad split line");
        auto id=std::stoul(line);
        auto map=tm2020::Map::load(folder/(std::to_string(id)+".tmmap"));
        auto replay=tm2020::Replay::load(folder/(std::to_string(id)+".tmreplay"));
        tm2020::Dataset data(std::move(map),std::move(replay));
        const auto& states=data.replay().states;
        ++result.maps;
        for(std::size_t i=0;i+5<states.size();++i) {
            const auto& now=states[i];
            const auto& next=states[i+5];
            if(next.time_ms>data.replay().finish_ms)break;
            if(next.time_ms-now.time_ms!=250)continue;
            // Exclude large discontinuities/respawn teleports where a conventional
            // target waypoint isn't a physically reachable future target.
            const double dx=next.position.x-now.position.x;
            const double dy=next.position.y-now.position.y;
            const double dz=next.position.z-now.position.z;
            const double d2=dx*dx+dy*dy+dz*dz;
            if(d2>250*250)continue;
            result.samples.push_back({tm2020::bc_features(now,next),
                {now.controls.steer,now.controls.gas,now.controls.brake}});
        }
    }
    if(result.maps==0||result.samples.size()<50)
        throw std::runtime_error("Insufficient supervised examples");
    return result;
}
struct Model {
    std::array<double,F> mean{};
    std::array<double,F> stddev{};
    std::array<std::array<double,3>,F> weight{};
};

static std::array<std::array<double,3>,F> solve(
    std::array<std::array<double,F>,F> x,
    std::array<std::array<double,3>,F> y) {
    // Partial-pivot Gaussian elimination with ridge-stabilized Gram matrix.
    for(int p=0;p<F;p++){
        int pivot=p;
        for(int i=p+1;i<F;i++)if(std::abs(x[i][p])>std::abs(x[pivot][p]))pivot=i;
        if(std::abs(x[pivot][p])<1e-11)
            throw std::runtime_error("Training matrix singular");
        std::swap(x[pivot],x[p]);std::swap(y[pivot],y[p]);
        const double diagonal=x[p][p];
        for(int col=p;col<F;col++)x[p][col]/=diagonal;
        for(auto& value:y[p])value/=diagonal;
        for(int row=0;row<F;row++){
            if(row==p)continue;
            const double factor=x[row][p];
            for(int col=p;col<F;col++)x[row][col]-=factor*x[p][col];
            for(int t=0;t<3;t++)y[row][t]-=factor*y[p][t];
        }
    }
    return y;
}
static Model fit(const DataSet& data,double lambda){
    Model model;
    const double n=double(data.samples.size());
    for(const auto& s:data.samples)for(int i=1;i<F;i++)model.mean[i]+=s.x[i]/n;
    for(const auto& s:data.samples)for(int i=1;i<F;i++){
        const double d=s.x[i]-model.mean[i];
        model.stddev[i]+=d*d/n;
    }
    model.stddev[0]=1;
    for(int i=1;i<F;i++){
        model.stddev[i]=std::sqrt(model.stddev[i]);
        if(model.stddev[i]<1e-8)model.stddev[i]=1;
    }
    std::array<std::array<double,F>,F> xtx{};
    std::array<std::array<double,3>,F> xty{};
    for(const auto& sample:data.samples){
        Features normalized{};
        for(int k=0;k<F;k++)normalized[k]=(sample.x[k]-model.mean[k])/model.stddev[k];
        for(int i=0;i<F;i++){
            for(int j=0;j<F;j++)xtx[i][j]+=normalized[i]*normalized[j];
            for(int j=0;j<3;j++)xty[i][j]+=normalized[i]*sample.y[j];
        }
    }
    for(int i=1;i<F;i++)xtx[i][i]+=lambda;
    model.weight=solve(xtx,xty);
    return model;
}
static Targets predict(const Model& m,const Features& x){
    Targets y{};
    for(int i=0;i<F;i++){
        const double normalized=(x[i]-m.mean[i])/m.stddev[i];
        for(int j=0;j<3;j++)y[j]+=normalized*m.weight[i][j];
    }
    y[0]=std::clamp(y[0],-1.,1.);
    for(int j=1;j<3;j++)y[j]=std::clamp(y[j],0.,1.);
    return y;
}
static void write_model(const Model& m,const fs::path& path){
    std::ofstream out(path,std::ios::binary);
    if(!out)throw std::runtime_error("Cannot save model");
    const char magic[8]={'T','M','B','C','0','0','1','\0'};
    out.write(magic,8);
    for(double x:m.mean)out.write(reinterpret_cast<const char*>(&x),8);
    for(double x:m.stddev)out.write(reinterpret_cast<const char*>(&x),8);
    for(const auto& weights:m.weight)for(double x:weights)
        out.write(reinterpret_cast<const char*>(&x),8);
}
struct Metrics {
    double steer_mae{},steer_baseline{},gas_accuracy{},gas_baseline{},brake_accuracy{},brake_baseline{};
};
static Metrics evaluate(const DataSet& d,const Model& model) {
    Metrics m;
    for(const auto& s:d.samples) {
        const auto p=predict(model,s.x);
        m.steer_mae+=std::abs(p[0]-s.y[0]);
        m.steer_baseline+=std::abs(s.y[0]);
        m.gas_accuracy+=(int(p[1]>=.5)==int(s.y[1]>=.5));
        m.gas_baseline+=(s.y[1]>=.5);
        m.brake_accuracy+=(int(p[2]>=.5)==int(s.y[2]>=.5));
        m.brake_baseline+=(s.y[2]<.5);
    }
    const double n=d.samples.size();
    m.steer_mae/=n;m.steer_baseline/=n;
    m.gas_accuracy/=n;m.gas_baseline/=n;
    m.brake_accuracy/=n;m.brake_baseline/=n;
    return m;
}
int main(int argc,char** argv){
    try{
        if(argc<3){
            std::cerr<<"Usage: tm2020_bc_train <dataset-directory> <output-model.tmbc> [lambda]\n";
            return 2;
        }
        const fs::path folder=argv[1],output=argv[2];
        const double lambda=argc>=4?std::stod(argv[3]):60.;
        if(lambda<=0 || !std::isfinite(lambda))throw std::invalid_argument("Invalid ridge coefficient");
        auto train=load(folder,"train");
        auto test=load(folder,"test");
        auto model=fit(train,lambda);
        const auto m=evaluate(test,model);
        fs::create_directories(output.parent_path());
        write_model(model,output);
        std::cout<<std::fixed<<std::setprecision(6)
                 <<"OFFLINE_BC_NATIVE_CPP20: train_maps="<<train.maps
                 <<" test_maps="<<test.maps
                 <<" train_samples="<<train.samples.size()
                 <<" test_samples="<<test.samples.size()
                 <<" steer_MAE="<<m.steer_mae
                 <<" zero_steer_MAE="<<m.steer_baseline
                 <<" gas_accuracy="<<m.gas_accuracy
                 <<" always_gas_accuracy="<<m.gas_baseline
                 <<" brake_accuracy="<<m.brake_accuracy
                 <<" never_brake_accuracy="<<m.brake_baseline
                 <<" model="<<output.string()<<"\n";
        if(!std::isfinite(m.steer_mae))return 1;
        std::cout<<"WARNING: Uses ground-truth future waypoints from replay. "
                 <<"Cannot run autonomously without trajectory planner. "
                 <<"Not RL or accurate Trackmania physics.\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr<<"ERROR: "<<e.what()<<"\n";return 1;
    }
}

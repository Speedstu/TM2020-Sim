// SPDX-License-Identifier: GPL-3.0-or-later
// Imitation initializer; demonstration targets are excluded at inference.
#include "tm2020/rl.hpp"
#include "fast_training.h"
#include <array>
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
struct Row{std::array<double,48>x;std::array<double,3> y;};
std::vector<Row> read(const std::filesystem::path& file){
 std::ifstream f(file);if(!f)throw std::runtime_error("Dataset not readable");std::string line;std::getline(f,line);
 if(!line.starts_with("x0,x1,"))throw std::runtime_error("Dataset schema differs");std::vector<Row> rows;
 while(std::getline(f,line)){std::stringstream s(line);std::string t;std::vector<double> v;
  while(std::getline(s,t,',')){double x=std::stod(t);if(!std::isfinite(x))throw std::runtime_error("Nonfinite dataset");v.push_back(x);}
  if(v.size()!=51)throw std::runtime_error("Dataset width differs");Row r;std::copy_n(v.begin(),48,r.x.begin());
  r.y={v[48]>.5?.95:-.95,v[49]>.5?.95:-.95,v[50]};
  for(size_t k=9;k<12;k++)r.x[k]=0.;rows.push_back(r);
 }
 if(rows.size()<20)throw std::runtime_error("Dataset too small");return rows;
}
double loss(const tm2020::rl::ActorCritic& p,const std::vector<Row>& rows){double result=0;
 for(auto& r:rows){auto d=p.deterministic(r.x);for(size_t k=0;k<3;k++)result+=std::pow(d.action[k]-r.y[k],2);}
 return result/(rows.size()*3);}
int main(int argc,char**argv)try{
 if(argc!=5)throw std::runtime_error("warmstart TRAIN.csv VALIDATION.csv OUTPUT EPOCHS");
 if(std::filesystem::equivalent(argv[1],argv[2]))throw std::runtime_error("Independent validation file required");
 const auto train=read(argv[1]),valid=read(argv[2]);const std::filesystem::path output=argv[3];
 if(std::filesystem::exists(output))throw std::runtime_error("Output must be new");std::filesystem::create_directories(output);
 size_t epochs=std::stoull(argv[4]);if(!epochs||epochs>20000)throw std::runtime_error("Bounded epochs required");
 tm2020::rl::ActorCritic p(48,3,128,2026);p.log_std.assign(3,std::log(.2));
 auto& w=p.actor.parameters;std::vector<double> m(w.size()),v(w.size());
 // These inputs are masked in the demonstrations. They must also have no
 // effect when the deployed policy receives its real previous controls.
 for(size_t h=0;h<128;h++)for(size_t k=9;k<12;k++)w[h*48+k]=0.;
 auto best=p;auto initial=loss(p,valid),selected=initial;size_t selected_epoch=0,update=0;
 std::vector<size_t> order(train.size());std::iota(order.begin(),order.end(),0);std::mt19937_64 rng(2026);
 for(size_t epoch=0;epoch<epochs;epoch++){
  std::shuffle(order.begin(),order.end(),rng);
  for(size_t at=0;at<order.size();at+=128){size_t end=std::min(at+128,order.size());std::vector<double> g(w.size());
   for(size_t i=at;i<end;i++){const auto& r=train[order[i]];auto z=p.actor.forward(r.x);std::array<double,3>d;
    for(size_t k=0;k<3;k++){double y=std::tanh(z[k]);d[k]=(y-r.y[k])*(1-y*y)/double(end-at);}
    p.actor.backward(r.x,d,g);}
   update++;double b1=1-std::pow(.9,double(update)),b2=1-std::pow(.999,double(update));
   for(size_t k=0;k<w.size();k++){m[k]=.9*m[k]+.1*g[k];v[k]=.999*v[k]+.001*g[k]*g[k];w[k]-=.0005*(m[k]/b1)/(std::sqrt(v[k]/b2)+1e-8);}
  }
  double current=loss(p,valid);if(current<selected){selected=current;best=p;selected_epoch=epoch+1;}
  if((epoch+1)%50==0)std::cout<<"BC epoch="<<epoch+1<<" train="<<loss(p,train)<<" validation="<<current<<std::endl;
 }
 const auto schema=std::string(TMFAST_SCHEMA)+"|policy_actions=pedals_direct3";
 best.save(output/"policy.tmppo",schema);p.save(output/"last.tmppo",schema);
 std::ofstream report(output/"report.json");report<<std::setprecision(17)<<"{\"trainRows\":"<<train.size()<<",\"validationRows\":"<<valid.size()
  <<",\"selectedEpoch\":"<<selected_epoch<<",\"initialValidationMse\":"<<initial<<",\"validationMse\":"<<selected
  <<",\"testMapsUsed\":false,\"closedLoopStrengthQualified\":false}\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

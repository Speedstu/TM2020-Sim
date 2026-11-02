#include "tm2020/trajectory_hybrid.hpp"
#include <memory>
struct BatchTracker {
    tm2020::hybrid::Tracker tracker;
    std::vector<tm2020::hybrid::Cursor> cursors;
};
extern "C" {
std::uint64_t tmhybrid_checksum(const unsigned char* bytes,std::size_t count){
    return tm2020::hybrid::Tracker::checksum(bytes,count);
}
void* tmhybrid_open(const char* path,unsigned count){
    try{if(!path||!count||count>64)return nullptr;auto b=std::make_unique<BatchTracker>();
        b->tracker=tm2020::hybrid::Tracker::load(path);b->cursors.resize(count);return b.release();}catch(...){return nullptr;}
}
void tmhybrid_close(void* p){delete static_cast<BatchTracker*>(p);}
int tmhybrid_reset(void* p,unsigned i){auto& b=*static_cast<BatchTracker*>(p);if(i>=b.cursors.size())return -1;b.cursors[i]={};return 0;}
int tmhybrid_commit(void* p,unsigned i,float steer){auto& b=*static_cast<BatchTracker*>(p);
    if(i>=b.cursors.size()||!std::isfinite(steer)||std::abs(steer)>1)return -1;
    b.cursors[i].previous_steer=steer;return 0;}
unsigned tmhybrid_cursor(void* p,unsigned i){auto& b=*static_cast<BatchTracker*>(p);
    return i<b.cursors.size()?b.cursors[i].index:UINT32_MAX;}
int tmhybrid_gains(void* p,const double* gains){
    auto& b=*static_cast<BatchTracker*>(p);if(!gains)return -1;
    for(unsigned i=0;i<6;++i){if(!std::isfinite(gains[i]))return -1;b.tracker.gains[i]=gains[i];}return 0;
}
int tmhybrid_actions(void* p,const float* states,const unsigned* milliseconds,float* controls,double* features,const double* residuals){
    auto& b=*static_cast<BatchTracker*>(p);if(!states||!milliseconds||!controls)return -1;
    for(std::size_t i=0;i<b.cursors.size();++i){
        tm2020::internal::Controls c{};std::array<double,12> x{};
        const bool ok=b.tracker.action(b.cursors[i],states+i*22,milliseconds[i],c,&x,residuals?residuals[i]:0.);
        if(!ok)c={};std::memcpy(controls+i*3,&c,12);if(features)std::copy(x.begin(),x.end(),features+i*12);
    }return 0;
}
int tmhybrid_govern_controls(void* p,const float* controls,const unsigned* milliseconds,float* output){
    auto& b=*static_cast<BatchTracker*>(p);
    if(!controls||!milliseconds||!output||(b.tracker.version!=5&&b.tracker.version!=6&&b.tracker.version!=7&&b.tracker.version!=8))return -1;
    for(std::size_t i=0;i<b.cursors.size();++i){
        tm2020::internal::Controls c{controls[i*3],controls[i*3+1],controls[i*3+2]};
        if(!tm2020::internal::valid(c))return -1;
        b.tracker.constrain(b.cursors[i],milliseconds[i],c);
        b.cursors[i].previous_steer=c.steer;
        std::memcpy(output+i*3,&c,12);
    }return 0;
}
}

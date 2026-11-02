#include "tm2020.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace tm2020 {
namespace {
constexpr double pi=3.14159265358979323846;
double squared_distance(Vec3 a,Vec3 b) {
    const double dx=a.x-b.x,dy=a.y-b.y,dz=a.z-b.z;
    return dx*dx+dy*dy+dz*dz;
}
double angle_diff(double a,double b){return std::remainder(a-b,2*pi);}
}
RoutePlan::RoutePlan(const Replay& demonstration) {
    const auto& obs=demonstration.states;
    if(obs.size()<2)throw std::invalid_argument("At least two vehicle states required");
    std::size_t seg=0;
    for(const auto& s:obs){
        if(s.time_ms>demonstration.finish_ms)break;
        if(!std::isfinite(s.position.x)||!std::isfinite(s.position.y)||
           !std::isfinite(s.position.z)||!std::isfinite(s.yaw_rad)||s.speed_kmh<0)
            throw std::invalid_argument("Invalid replay route sample");
        Node point;
        point.pos=s.position;
        point.heading=s.yaw_rad;
        point.speed_kmh=s.speed_kmh;
        if(!nodes_.empty()){
            const auto& prior=nodes_.back();
            const double traveled=std::sqrt(squared_distance(point.pos,prior.pos));
            const auto& last_state=obs[nodes_.size()-1];
            const auto dt=(s.time_ms-last_state.time_ms)/1000.;
            // A gap or implausibly large displacement indicates a teleport.
            const bool teleport=dt<=0 || dt>0.075 ||
                traveled>((std::max(s.speed_kmh,prior.speed_kmh)/3.6)*dt+12.0);
            if(teleport)++seg;
            point.distance=teleport?0.0:prior.distance+traveled;
        }
        point.segment_id=seg;
        nodes_.push_back(point);
    }
    if(nodes_.size()<2)throw std::invalid_argument("Not enough in-race replay samples");
    segment_count_=seg+1;
    std::vector<std::size_t> order(nodes_.size());
    for(std::size_t i=0;i<order.size();++i)order[i]=i;
    index_.reserve(order.size());
    index_root_=build_index(order,0,order.size(),0);
}

int RoutePlan::build_index(std::vector<std::size_t>& order,
                          std::size_t begin,std::size_t end,int depth){
    if(begin>=end)return -1;
    const std::size_t mid=begin+(end-begin)/2;
    const int axis=depth%3;
    auto coord=[&](const Vec3& v){return axis==0?v.x:axis==1?v.y:v.z;};
    std::nth_element(order.begin()+begin,order.begin()+mid,order.begin()+end,
       [&](std::size_t a,std::size_t b){
           const double pa=coord(nodes_[a].pos),pb=coord(nodes_[b].pos);
           return pa==pb?a<b:pa<pb;
       });
    const int current=static_cast<int>(index_.size());
    index_.push_back({});
    const std::size_t sample=order[mid];
    const int left=build_index(order,begin,mid,depth+1);
    const int right=build_index(order,mid+1,end,depth+1);
    auto& node=index_[current];
    node.sample=sample;
    node.left=left;
    node.right=right;
    node.min=nodes_[sample].pos;
    node.max=nodes_[sample].pos;
    for(int sub:{left,right})if(sub>=0){
        const auto& branch=index_[sub];
        node.min.x=std::min(node.min.x,branch.min.x);
        node.min.y=std::min(node.min.y,branch.min.y);
        node.min.z=std::min(node.min.z,branch.min.z);
        node.max.x=std::max(node.max.x,branch.max.x);
        node.max.y=std::max(node.max.y,branch.max.y);
        node.max.z=std::max(node.max.z,branch.max.z);
    }
    return current;
}

void RoutePlan::search_index(int current,Vec3 position,double yaw,
                             double& best,std::size_t& best_sample)const{
    if(current<0)return;
    const auto& index=index_[current];
    auto lower_bound=[&](const KDNode& n){
        double distance=0;
        auto offset=[](double x,double low,double high){
            return x<low?low-x:x>high?x-high:0.0;
        };
        const double dx=offset(position.x,n.min.x,n.max.x);
        const double dy=offset(position.y,n.min.y,n.max.y);
        const double dz=offset(position.z,n.min.z,n.max.z);
        distance=dx*dx+dy*dy+dz*dz;
        return distance;
    };
    if(lower_bound(index)>best)return;
    const auto sample=index.sample;
    const auto& p=nodes_[sample];
    const double score=squared_distance(position,p.pos)+25*(1-std::cos(angle_diff(p.heading,yaw)));
    if(score<best || (score==best&&sample<best_sample)){
        best=score;
        best_sample=sample;
    }
    const int a=index.left,b=index.right;
    const double da=a>=0?lower_bound(index_[a]):std::numeric_limits<double>::infinity();
    const double db=b>=0?lower_bound(index_[b]):std::numeric_limits<double>::infinity();
    if(da<db){
        if(da<=best)search_index(a,position,yaw,best,best_sample);
        if(db<=best)search_index(b,position,yaw,best,best_sample);
    }else{
        if(db<=best)search_index(b,position,yaw,best,best_sample);
        if(da<=best)search_index(a,position,yaw,best,best_sample);
    }
}

RouteTarget RoutePlan::target(Vec3 car_position,double car_yaw,double lookahead_m)const {
    if(!std::isfinite(car_position.x)||!std::isfinite(car_position.y)||
       !std::isfinite(car_position.z)||!std::isfinite(car_yaw)||
       !std::isfinite(lookahead_m)||lookahead_m<0||lookahead_m>1000)
        throw std::invalid_argument("Nonfinite or out-of-range route query");
    if(nodes_.empty())throw std::runtime_error("Empty route");
    std::size_t nearest=0;
    double best=std::numeric_limits<double>::infinity();
    // Exact 3D KD-tree search using Euclidean bounding boxes. The directional
    // penalty is nonnegative, so it never invalidates the spatial bound.
    search_index(index_root_,car_position,car_yaw,best,nearest);
    const Node& close=nodes_[nearest];
    const double requested=close.distance+lookahead_m;
    std::size_t destination=nearest;
    while(destination+1<nodes_.size() &&
          nodes_[destination+1].segment_id==close.segment_id &&
          nodes_[destination].distance<requested) {
        ++destination;
    }
    const Node& waypoint=nodes_[destination];
    RouteTarget result;
    result.waypoint=waypoint.pos;
    result.yaw_rad=waypoint.heading;
    result.target_speed_kmh=waypoint.speed_kmh;
    result.distance_ahead_m=waypoint.distance-close.distance;
    result.lateral_error_m=std::sqrt(squared_distance(car_position,close.pos));
    result.nearest_sample=nearest;
    result.target_sample=destination;
    result.segment_end=destination+1==nodes_.size() ||
        nodes_[destination+1].segment_id!=waypoint.segment_id;
    return result;
}

State RoutePlan::as_desired_future(const State& current,double lookahead_m)const {
    const auto t=target(current.position,current.yaw_rad,lookahead_m);
    State desired=current;
    desired.position=t.waypoint;
    desired.yaw_rad=t.yaw_rad;
    desired.speed_kmh=t.target_speed_kmh;
    return desired;
}
} // namespace tm2020

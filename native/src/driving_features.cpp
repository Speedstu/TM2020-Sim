#include "tm2020/driving_features.hpp"
#include <cmath>
namespace tm2020 {
std::array<double,8> driving_features(const RoutePlan& route,const State& s){
    std::array<double,8> x{};const std::array distances{10.,30.,60.};
    const double co=std::cos(s.yaw_rad),si=std::sin(s.yaw_rad);
    for(std::size_t i=0;i<3;i++){
        const auto t=route.target(s.position,s.yaw_rad,distances[i]);
        const double dx=t.waypoint.x-s.position.x,dz=t.waypoint.z-s.position.z;
        x[i*2]=(co*dx-si*dz)/60.;x[i*2+1]=(si*dx+co*dz)/60.;
    }
    x[6]=s.speed_kmh/360.;x[7]=s.ground_contact?1.:0.;return x;
}
}

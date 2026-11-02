#include "tm2020/recovered_step.hpp"
#include <bit>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool ok){if(!ok)throw std::runtime_error("Vehicle substep regression failed");}
int main()try{
    const auto dt=native_vehicle_interval;
    auto a=select_vehicle_substeps(0.f,1.f,1.f,dt);
    check(a.substeps==1&&a.repeated_scaled_interval==0&&vehicle_last_substep_interval(a)==dt);
    a=select_vehicle_substeps(1.f,1.f,1.f,dt);
    check(a.substeps==2&&a.repeated_scaled_interval==dt/2&&vehicle_last_substep_interval(a)==dt/2);
    check(select_vehicle_substeps(std::nextafter(1.f,0.f),1.f,1.f,dt).substeps==1);
    a=select_vehicle_substeps(999.f,1.f,1.f,dt);
    check(a.substeps==1000&&a.timestamp_subtrahend_nanoseconds<0);
    check(select_vehicle_substeps(1000000.f,1.f,1.f,dt).substeps==1000);
    check(vehicle_last_substep_interval(a)!=a.repeated_scaled_interval);
    VehicleSubstepMotion motion{{3,4,0},{0,0,0},{0,0,12},{0,8,15}};
    check(scaled_vehicle_substep_motion(motion,1.f,dt)==34.f*dt);
    check(select_vehicle_substeps(motion,1.f,1.f,dt).substeps==1);
    for(const auto row:std::array<std::array<float,4>,6>{{
        {-1,1,1,dt},{0,0,1,dt},{0,1,0,dt},{0,1,1,0},
        {1e9f,1e-6f,1,dt},{std::numeric_limits<float>::quiet_NaN(),1,1,dt}}}){
        bool rejected=false;try{select_vehicle_substeps(row[0],row[1],row[2],row[3]);}
        catch(const std::invalid_argument&){rejected=true;}check(rejected);
    }
    std::cout<<"PASS VEHICLE SUBSTEP SELECTION bounded_arithmetic_slice=true\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}

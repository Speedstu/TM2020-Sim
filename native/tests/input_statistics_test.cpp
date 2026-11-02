#include "tm2020/input_statistics.hpp"
#include <stdexcept>
#include <iostream>
void check(bool ok){if(!ok)throw std::runtime_error("Input statistics differ");}
int main(){
    tm2020::internal::InputStatistics s;
    s.observe(1,0,0);s.observe(1,0,1.f/127);s.observe(0,1,0);s.observe(0,1,-1.f/127);
    s.observe(1,0,0);s.observe(1,0,1);s.observe(1,0,-1);
    check(s.counts[0]==7&&s.counts[1]==6&&s.counts[2]==385);
    check(s.counts[3]==3&&s.counts[4]==2&&s.counts[5]==2&&s.counts[6]==2);
    auto counts=s.snapshot();
    check(counts[7]==5&&counts[8]==2&&counts[10]==4&&counts[136]==1&&counts[263]==1);
    check(counts[tm2020::internal::InputStatistics::steer_hold_offset]==7);
    check(counts[tm2020::internal::InputStatistics::gas_press_offset+1]==1);
    check(counts[tm2020::internal::InputStatistics::gas_press_offset+2]==1);
    check(counts[tm2020::internal::InputStatistics::gas_release_offset+1]==1);
    check(counts[tm2020::internal::InputStatistics::brake_press_offset+1]==1);
    check(counts[tm2020::internal::InputStatistics::brake_release_offset+1]==1);
    check(counts[tm2020::internal::InputStatistics::brake_release_offset+2]==1);
    std::cout<<"PASS input statistics: holds, pedals, small reversals, saturated steering\n";
}

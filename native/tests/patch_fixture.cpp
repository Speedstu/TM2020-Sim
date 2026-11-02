#include "tm2020/recovered_patches.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
template<class T>void read(std::istream& in,T& value){if(!in.read(reinterpret_cast<char*>(&value),sizeof(value)))throw std::runtime_error("Truncated patch fixture");}
template<class T>void write(std::ostream& out,const T& value){out.write(reinterpret_cast<const char*>(&value),sizeof(value));}
int main(int argc,char** argv)try{
    if(argc!=3)throw std::runtime_error("Usage: patch_fixture input output");std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t cases{};read(in,cases);if(cases>100000)throw std::runtime_error("Too many patch cases");
    for(std::uint32_t n=0;n<cases;n++){
        std::array<std::uint32_t,7> objects{};SurfaceResponseParameters parameters{};std::uint32_t count{};read(in,objects);read(in,parameters);read(in,count);if(count>512)throw std::runtime_error("Too many patch fixture contacts");
        std::vector<ConvexContact> geometry(count);for(auto& g:geometry)read(in,g);
        const auto patches=build_contact_patches(geometry,SurfaceMaterialTable{},{objects[0],objects[1],std::uint8_t(objects[2])},{objects[3],objects[4],std::uint8_t(objects[5])},objects[6],parameters);
        write(out,std::uint32_t(patches.size()));for(const auto& p:patches){write(out,p.normal);write(out,p.response);write(out,std::uint32_t(p.points.size()));write(out,std::uint32_t(p.first_chunk));for(const auto& point:p.points)write(out,point);}
    }
    if(!out)throw std::runtime_error("Cannot write patch fixture");std::cout<<"PASS PATCH_FIXTURE cases="<<cases<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

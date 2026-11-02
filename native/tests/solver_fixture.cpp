#include "tm2020/recovered_solver.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string_view>
using namespace tm2020::recovered;
template<class T>void read(std::istream& in,T& value){if(!in.read(reinterpret_cast<char*>(&value),sizeof(value)))throw std::runtime_error("Truncated solver fixture");}
template<class T>void write(std::ostream& out,const T& value){out.write(reinterpret_cast<const char*>(&value),sizeof(value));}
template<class T>void array(std::istream& in,std::vector<T>& a){std::uint32_t count{};read(in,count);if(count>3)throw std::runtime_error("Solver fixture count exceeds domain");a.resize(count);for(auto& x:a)read(in,x);}
template<class F>void fields(ContactIsland& i,F&& f){f(i.static_friction_normals);f(i.static_final_normals);f(i.static_friction);f(i.static_normals);f(i.dynamic_friction_normals);f(i.dynamic_final_normals);f(i.dynamic_normals);f(i.dynamic_friction);}
template<class F>void fields(ConstraintIsland& i,F&& f){fields(i.contacts,f);f(i.late_points);f(i.early_points);f(i.angular_couplings);f(i.angular_constraints);}
int main(int argc,char** argv)try{
    if(argc!=3&&(argc!=4||std::string_view(argv[3])!="--joints"))throw std::runtime_error("Usage: solver_fixture input output [--joints]");
    std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t cases{};read(in,cases);
    if(cases>100000)throw std::runtime_error("Too many solver fixtures");
    for(std::uint32_t n=0;n<cases;n++){
        std::array<RigidState,3> states{};std::array<VelocityCoefficients,3> coefficients{};ContactSolverIterations config{};std::uint32_t count{};
        read(in,states);read(in,coefficients);read(in,config);read(in,count);if(count>3)throw std::runtime_error("Too many solver islands");
        const auto process=[&]<class I>(std::vector<I> islands){
            for(auto& i:islands)fields(i,[&](auto& a){array(in,a);});
            if constexpr(std::is_same_v<I,ConstraintIsland>)solve_constraint_islands(states,coefficients,islands,config);
            else solve_contact_islands(states,coefficients,islands,config);
            write(out,states);for(auto& i:islands)fields(i,[&](auto& a){for(const auto& x:a)write(out,x);});
        };
        if(argc==4)process(std::vector<ConstraintIsland>(count));else process(std::vector<ContactIsland>(count));
    }
    if(!out)throw std::runtime_error("Cannot write solver fixture");std::cout<<"PASS SOLVER_FIXTURE cases="<<cases<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}

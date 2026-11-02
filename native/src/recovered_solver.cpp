#include "tm2020/recovered_solver.hpp"
#include <algorithm>
#include <stdexcept>
namespace tm2020::recovered {
void solve_contact_islands(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,
    std::span<ContactIsland> islands,ContactSolverIterations iterations){
    if(states.size()!=coefficients.size()||states.size()>1000000||islands.size()>1024||
        iterations.velocity>128||iterations.static_friction>128||iterations.dynamic_friction>128)
        throw std::invalid_argument("Contact island scheduler exceeds qualified domain");
    std::size_t total{};
    for(const auto& i:islands){
        total+=i.static_friction_normals.size()+i.static_final_normals.size()+i.static_friction.size()+i.static_normals.size()+
            i.dynamic_friction_normals.size()+i.dynamic_final_normals.size()+i.dynamic_normals.size()+i.dynamic_friction.size();
        if(total>1000000)throw std::invalid_argument("Too many island constraints");
    }
    if(!iterations.velocity)return;
    auto next=std::vector<RigidState>(states.begin(),states.end());auto staged=std::vector<ContactIsland>(islands.begin(),islands.end());
    for(std::uint32_t iteration=0;iteration<iterations.velocity;iteration++){
        if(iteration<iterations.dynamic_friction)for(auto& i:staged){
            solve_dynamic_normals(next,coefficients,i.dynamic_friction_normals);
            solve_dynamic_friction(next,i.dynamic_friction,i.dynamic_normals);
        }
        if(iteration<iterations.static_friction)for(auto& i:staged){
            solve_static_normals(next,coefficients,i.static_friction_normals);
            solve_static_friction(next,i.static_friction,i.static_normals);
        }
        // Native +0x120/+0x130/+0xc0/+0x30 general constraint spans are empty.
        for(auto& i:staged)solve_static_unilateral(next,i.static_normals);
        for(auto& i:staged){
            solve_dynamic_normals(next,coefficients,i.dynamic_final_normals);
            solve_dynamic_unilateral(next,i.dynamic_normals);
        }
        // Native external 0x20-byte callback constraint list is empty.
        for(auto& i:staged)solve_static_normals(next,coefficients,i.static_final_normals);
    }
    std::copy(next.begin(),next.end(),states.begin());
    for(std::size_t k=0;k<staged.size();k++)islands[k]=std::move(staged[k]);
}
void solve_constraint_islands(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,
    std::span<ConstraintIsland> islands,ContactSolverIterations iterations){
    if(states.size()!=coefficients.size()||states.size()>1000000||islands.size()>1024||
        iterations.velocity>128||iterations.static_friction>128||iterations.dynamic_friction>128)
        throw std::invalid_argument("Constraint island scheduler exceeds qualified domain");
    std::size_t total{};
    for(const auto& i:islands){const auto& c=i.contacts;
        total+=c.static_friction_normals.size()+c.static_final_normals.size()+c.static_friction.size()+c.static_normals.size()+
            c.dynamic_friction_normals.size()+c.dynamic_final_normals.size()+c.dynamic_normals.size()+c.dynamic_friction.size()+
            i.early_points.size()+i.late_points.size()+i.angular_couplings.size()+i.angular_constraints.size();
        if(total>1000000)throw std::invalid_argument("Too many island constraints");
    }
    if(!iterations.velocity)return;
    auto next=std::vector<RigidState>(states.begin(),states.end());auto staged=std::vector<ConstraintIsland>(islands.begin(),islands.end());
    for(std::uint32_t iteration=0;iteration<iterations.velocity;iteration++){
        if(iteration<iterations.dynamic_friction)for(auto& i:staged){
            solve_dynamic_normals(next,coefficients,i.contacts.dynamic_friction_normals);
            solve_dynamic_friction(next,i.contacts.dynamic_friction,i.contacts.dynamic_normals);
        }
        if(iteration<iterations.static_friction)for(auto& i:staged){
            solve_static_normals(next,coefficients,i.contacts.static_friction_normals);
            solve_static_friction(next,i.contacts.static_friction,i.contacts.static_normals);
        }
        for(auto& i:staged)solve_angular_couplings(next,coefficients,i.angular_couplings);
        for(auto& i:staged)solve_angular_constraints(next,coefficients,i.angular_constraints);
        for(auto& i:staged)solve_point_constraints(next,coefficients,i.early_points);
        for(auto& i:staged){solve_point_constraints(next,coefficients,i.late_points);solve_static_unilateral(next,i.contacts.static_normals);}
        for(auto& i:staged){solve_dynamic_normals(next,coefficients,i.contacts.dynamic_final_normals);solve_dynamic_unilateral(next,i.contacts.dynamic_normals);}
        // The original separate callback constraint list is empty here.
        for(auto& i:staged)solve_static_normals(next,coefficients,i.contacts.static_final_normals);
    }
    std::copy(next.begin(),next.end(),states.begin());for(std::size_t k=0;k<staged.size();k++)islands[k]=std::move(staged[k]);
}
}

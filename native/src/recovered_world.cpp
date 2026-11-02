#include "tm2020/recovered_world.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
template<std::size_t N>void bounded(const std::array<float,N>& a){for(float x:a)require(std::isfinite(x)&&std::abs(x)<=1e6f,"Rigid mesh world state exceeds finite domain");}
}
RigidMeshWorld::RigidMeshWorld(const ConvexTopologyView& shape,const AabbPrimitive& bounds,
    std::span<const ConvexVector> vertices,std::span<const IndexedTriangle> triangles,const MeshTransform& transform,
    const RigidMeshConfiguration& config):
    body_vertices_(shape.axes.vertices.begin(),shape.axes.vertices.end()),body_normals_(shape.axes.face_normals.begin(),shape.axes.face_normals.end()),
    body_directions_(shape.axes.edge_directions.begin(),shape.axes.edge_directions.end()),mesh_vertices_(vertices.begin(),vertices.end()),
    edges_(shape.edges.begin(),shape.edges.end()),bounds_(bounds),mesh_transform_(transform),configuration_(config){
    require(shape.faces.size()<=4096&&shape.edges.size()<=16384&&shape.axes.vertices.size()<=4096,"World convex topology exceeds domain");
    require(config.velocity.flags==0&&!config.velocity.sleeping,"World requires an awake body with velocity/pose enabled");
    require(config.position_iterations<=128&&config.velocity_iterations.velocity<=128&&config.velocity_iterations.static_friction<=128&&config.velocity_iterations.dynamic_friction<=128,"World solver iterations exceed bound");
    require(std::isfinite(config.restitution_speed_threshold)&&config.restitution_speed_threshold>=0,"Invalid restitution threshold");
    for(float x:config.velocity.coefficients)require(std::isfinite(x)&&x>=0,"Invalid world velocity coefficient");
    require(config.velocity.coefficients[3]>0,"World body inverse mass must be positive");
    bounded(config.model_center);
    for(std::size_t i=0;i<3;i++)for(std::size_t j=0;j<3;j++){
        const auto& r=transform.rotation;const float dot=(r[i*3]*r[j*3]+r[i*3+1]*r[j*3+1])+r[i*3+2]*r[j*3+2];
        require(std::isfinite(dot)&&std::abs(dot-(i==j?1.f:0.f))<=2e-4f,"World mesh transform must be rigid");
    }
    bounded(bounds.center);bounded(bounds.half_extent);for(float x:bounds.half_extent)require(x>=0,"Negative world body bound");
    for(const auto& p:body_vertices_)for(std::size_t k=0;k<3;k++)require(std::abs(p[k]-bounds.center[k])<=bounds.half_extent[k]+1e-5f,"World broadphase bounds do not contain body vertices");
    face_indices_.reserve(shape.faces.size());for(const auto& f:shape.faces)face_indices_.emplace_back(f.vertices.begin(),f.vertices.end());
    for(std::size_t k=0;k<shape.faces.size();k++)faces_.push_back({shape.faces[k].normal_index,shape.faces[k].keep_normal,face_indices_[k]});
    mesh_triangles_=cook_triangles(mesh_vertices_,triangles);mesh_tree_=build_aabb_tree(triangle_aabbs(mesh_vertices_,triangles));
    // Validate all shape and rigid transform/index contracts before construction
    // succeeds; temporary contacts are discarded, and no simulation is advanced.
    collide_convex_mesh({body(),{},config.body_surface_id},{mesh_vertices_,mesh_triangles_,mesh_tree_,transform},bounds_,false);
    std::array<RigidState,1> check_state{};solve_static_positions(check_state,std::array<VelocityCoefficients,1>{config.velocity.coefficients},{},config.position,config.position_math);
    ForceAccumulator zero{};integrate_forces(check_state[0],zero,config.velocity,config.environment,0);
    RigidWorld validation(1);validation.reset(check_state,std::array{config.model});
}
ConvexTopologyView RigidMeshWorld::body()const{return {{body_vertices_,body_normals_,body_directions_},faces_,edges_};}
void RigidMeshWorld::validate_state(const RigidState& s)const{
    bounded(s.rotation);bounded(s.position);bounded(s.quaternion);bounded(s.linear_velocity);bounded(s.angular_velocity);
    float norm=0;for(float x:s.quaternion)norm+=x*x;require(std::abs(norm-1.f)<=2e-4f,"World quaternion must be normalized");
    std::array<float,9> rotation{};quaternion_to_matrix(rotation,s.quaternion);for(std::size_t k=0;k<9;k++)require(std::abs(rotation[k]-s.rotation[k])<=2e-4f,"World matrix and quaternion disagree");
}
void RigidMeshWorld::reset(const RigidState& s){validate_state(s);state_=s;auxiliary_={};tick_=0;}
RigidMeshStepReport RigidMeshWorld::step(float interval,ForceAccumulator& forces){
    require(std::isfinite(interval)&&interval>0&&interval<=1,"Invalid world interval");require(tick_!=std::numeric_limits<std::uint64_t>::max(),"World tick overflow");
    std::array states{state_};auto consumed=forces;auto auxiliary=auxiliary_;const auto& c=configuration_;const std::array<VelocityCoefficients,1> coefficients{c.velocity.coefficients};
    integrate_forces(states[0],consumed,c.velocity,c.environment,interval);
    const std::array<std::array<float,3>,1> centers{c.model_center};shift_model_center_frame(states,centers,false);
    auto geometry_origin=states;shift_model_center_frame(geometry_origin,centers,true);
    const auto& pose=geometry_origin[0];const auto collision=collide_convex_mesh({body(),{pose.rotation,pose.position},c.body_surface_id},
        {mesh_vertices_,mesh_triangles_,mesh_tree_,mesh_transform_},bounds_);
    const auto patches=build_contact_patches(collision.contacts,c.materials,c.body_object,c.mesh_object,c.runtime_class_id,c.surface_parameters);
    std::array<ContactIsland,1> islands{};std::vector<StaticPositionConstraint> positions;RigidMeshStepReport report{tick_+1,collision.contacts.size(),patches.size(),0,0};
    for(const auto& patch:patches)for(const auto& point:patch.points){
        auto& island=islands[0];const auto normal=std::uint32_t(island.static_normals.size());
        const auto prepared=prepare_static_contact({0,0,point.world_point,patch.normal,point.separation,patch.response.friction,patch.response.restitution},states,coefficients,interval,c.restitution_speed_threshold,normal);
        island.static_normals.push_back(prepared.normal);for(std::size_t k=0;k<prepared.friction_count;k++)island.static_friction.push_back(prepared.friction[k]);positions.push_back(prepared.position);
    }
    report.normal_constraints=islands[0].static_normals.size();report.friction_axes=islands[0].static_friction.size();
    solve_contact_islands(states,coefficients,islands,c.velocity_iterations);
    integrate_pose(states[0],c.model,auxiliary,interval);
    std::array<PositionIsland,1> position_islands{};position_islands[0].static_contacts=std::move(positions);
    solve_position_islands(states,coefficients,position_islands,c.position_iterations,c.position,c.position_math);
    shift_model_center_frame(states,centers,true);
    validate_state(states[0]);state_=states[0];auxiliary_=auxiliary;forces=consumed;tick_++;return report;
}
RigidMeshSnapshot RigidMeshWorld::snapshot()const{RigidMeshSnapshot out;out.state=state_;out.auxiliary=auxiliary_;out.tick=tick_;out.identity=identity_;return out;}
void RigidMeshWorld::restore(const RigidMeshSnapshot& s){require(s.identity==identity_,"World snapshot belongs to different geometry/settings");validate_state(s.state);bounded(s.auxiliary);state_=s.state;auxiliary_=s.auxiliary;tick_=s.tick;}
}

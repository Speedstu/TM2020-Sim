#include <tm2020.hpp>
#include <tm2020/experimental_sim.hpp>
#include <tm2020/bridge.h>
#include <tm2020/route_controller.hpp>
#include <tm2020/rl.hpp>
#include <tm2020/policy.h>
#include <tm2020/trainer.h>
#include <tm2020/visual_state.hpp>
#include <tm2020/recovered_rigid.hpp>
#include <tm2020/recovered_contacts.hpp>
#include <tm2020/recovered_jacobian.hpp>
#include <tm2020/recovered_position.hpp>
#include <tm2020/recovered_collision.hpp>
#include <tm2020/recovered_mesh.hpp>
#include <tm2020/recovered_raycast.hpp>
#include <tm2020/recovered_convex.hpp>
#include <tm2020/recovered_polygon.hpp>
#include <tm2020/recovered_vehicle.hpp>
#include <tm2020/recovered_material.hpp>
#include <tm2020/recovered_features.hpp>
#include <tm2020/recovered_convex_collision.hpp>
#include <tm2020/recovered_solver.hpp>
#include <tm2020/recovered_world.hpp>
#include <tm2020/recovered_wheel.hpp>
#include <tm2020/recovered_joint_position.hpp>
#include <tm2020/recovered_frames.hpp>
#include <tm2020/recovered_wheel_material.hpp>
#include <tm2020/recovered_resistance.hpp>
#include <tm2020/surface_materials.hpp>
#include <tm2020/recovered_step.hpp>
#include <tm2020/recovered_activation.hpp>
#include <tm2020/recovered_steering.hpp>
#ifdef _WIN32
#include <tm2020/read_only_live.hpp>
#include <type_traits>
#endif
#include <cmath>
#include <iostream>
int main() {
  static_assert(TM2020_TRAINER_API_VERSION==1u);
  {
  if(tm2020_trainer_version()!=TM2020_TRAINER_API_VERSION)return 37;
  tm2020_trainer_handle trainer{};
  if(tm2020_trainer_create(13,3,16,7,"installed-consumer-v1",&trainer))return 38;
  const std::array<double,13> obs{};std::array<double,3> action{};double value{};
  const bool sampled=tm2020_trainer_sample(trainer,obs.data(),13,action.data(),3,&value)==0;
  const bool canceled=sampled && tm2020_trainer_cancel(trainer)==0;
  tm2020_trainer_close(trainer);
  if(!canceled || !std::isfinite(value))return 39;
  }
  if(std::abs(tm2020::analog_steer_from_raw(0) + 1.0/255) > 1e-12) return 1;
  tm2020::experimental::Sandbox sandbox(1);
  if(tm2020::experimental::faithful_trackmania_physics) return 3;
  if(sandbox.size()!=1) return 4;
  tm2020::PurePursuitConfig config{40,-7.5};
  if(config.lookahead_m!=40 || TM2020_BRIDGE_API_VERSION!=3) return 5;
#ifdef _WIN32
  static_assert(!std::is_copy_constructible_v<tm2020::live::ReadOnlyObserver>);
#endif
  tm2020::rl::ActorCritic policy(8,1,8);
  std::array<double,8> observation{};std::array<double,1> action{};double value{};
  policy.predict_into(observation,action,value);
  if(!std::isfinite(action[0])||std::abs(action[0])>1||!std::isfinite(value))return 6;
  if(TM2020_POLICY_API_VERSION!=1||tm2020::live::visual_state_bytes!=0x360)return 7;
  tm2020::recovered::RigidWorld world(1);
  tm2020::recovered::BodyParameters body{{0,0,0},100};
  world.reset(std::array{tm2020::recovered::RigidState{}},std::array{body});
  tm2020::recovered::VelocityStepParameters parameters;
  parameters.coefficients={1,1,1,1};parameters.model_gravity_scale=1;parameters.item_gravity_multiplier=1;
  std::array<tm2020::recovered::ForceAccumulator,1> forces{};
  world.step_force_then_pose(.25f,forces,std::array{parameters},{{0,-10,0},false,.01f,.9f});
  if(world.states()[0].position[1]!=-.625f||tm2020::recovered::full_trackmania_physics)return 8;
  if(tm2020::recovered::select_pose_fraction({100,0,0},.5f,.01f)!=.005f)return 9;
  std::array<tm2020::recovered::RigidState,1> contact_body{};contact_body[0].linear_velocity[1]=-1;
  std::array<tm2020::recovered::StaticNormalConstraint,1> contact{{{0,{0,0,0},{0,1,0},0,1,0}}};
  tm2020::recovered::solve_static_normals(contact_body,std::array<tm2020::recovered::VelocityCoefficients,1>{{{0,0,0,1}}},contact);
  if(contact_body[0].linear_velocity[1]!=0)return 10;
  using namespace tm2020::recovered;
  SphereContact geometry{};
  {
    std::array<WakeIndexState,1> wake_indices{};std::vector<std::uint32_t> wake_queue;
    const std::array<std::uint32_t,1> reverse_handles{77};
    if(!enqueue_body_wake(true,0,wake_indices,reverse_handles,wake_queue)||wake_queue[0]!=77)return 41;
    std::array<std::uint32_t,1> active{};std::uint32_t active_count=0;
    if(!activate_body_slot(wake_indices[0],9,active,active_count)||active_count!=1||active[0]!=9)return 42;
    RaySphereHit sphere_ray{};
    if(!raycast_sphere({0,0,0},1,7,{-2,0,0},{4,0,0},{0,0,0},255,sphere_ray)
        ||sphere_ray.fraction!=.25f||sphere_ray.material!=7)return 43;
  }
  if(!collide_spheres({{0,0,0},1,1},{{1,0,0},1,2},geometry)||geometry.normal[0]!=-1)return 11;
  const std::array<VelocityCoefficients,1> coefficients{{{.1f,.1f,.1f,1}}};
  contact_body[0].linear_velocity={1,-2,0};
  auto prepared=prepare_static_contact({0,0,{0,-1,0},{0,1,0},.1f,.5f,.5f},contact_body,coefficients,.01f,1);
  std::array normal{prepared.normal};solve_static_unilateral(contact_body,normal);
  solve_static_friction(contact_body,prepared.friction,normal);
  solve_static_positions(contact_body,coefficients,std::array{prepared.position},{0,.1f,.2f});
  if(contact_body[0].position[1]<=0||prepared.friction_count!=2)return 12;
  correct_rotation(contact_body[0],{.001f,0,0});
  const std::array<ConvexVector,3> mesh_vertices{{{-2,0,-2},{-2,0,2},{2,0,0}}};
  const std::array<IndexedTriangle,1> indexed{{{{0,1,2},17,0}}};
  const auto cooked=cook_triangles(mesh_vertices,indexed);
  RayTriangleHit ray_hit;
  if(!raycast_cooked_triangle(mesh_vertices,cooked[0],{0,1,0},{0,-2,0},true,ray_hit))return 40;
  const auto bounds=triangle_aabbs(mesh_vertices,indexed);const auto tree=build_aabb_tree(bounds);
  if(collide_sphere_mesh({{0,.5f,0},1,1},{mesh_vertices,cooked,tree,{}}).size()!=1)return 13;
  if(project_vertices(mesh_vertices,{0,1,0}).maximum!=0)return 14;
  const std::array<ConvexVector,1> axis{{{0,1,0}}};
  if(!separating_axes({mesh_vertices,axis,{}},{mesh_vertices,axis,{}}).overlap)return 15;
  if(classify_point({0,0,0},{{1,0,0},0})!=PlaneSide::on_plane||split_polygon(mesh_vertices,{{1,0,0},0}).positive.empty())return 16;
  if(face_contacts(mesh_vertices,mesh_vertices,{0,1,0},{1,0,0,0,1,0,0,0,1,0,0,0}).empty())return 17;
  if(evaluate_curve(std::array<CurvePoint,2>{{{0,0},{1,1}}},.5f)!=.5f)return 18;
  ForceAccumulator spring{};std::array<SuspensionWheelState,4> wheels{};for(auto& wheel:wheels)wheel={.1f,.5f,true};
  if(!apply_suspension_mode2(spring,{}, {}, {1,0,0},{2,true,40,1,.2f},wheels,0)||spring.angular[2]!=3.5f)return 19;
  const auto response=surface_response(SurfaceMaterialTable{},1,2,{0x0a020000,9,1},{0,0,0},0x30abc000);
  if(response.friction!=.55f||response.restitution!=.25f)return 20;
  if(closest_edges({{0,0,0},{1,0,0},1},{{3,2,0},{-1,0,0},1}).squared_distance!=5)return 21;
  const std::array<ConvexVector,8> cube{{{-1,-1,-1},{1,-1,-1},{-1,1,-1},{1,1,-1},{-1,-1,1},{1,-1,1},{-1,1,1},{1,1,1}}};
  const std::array<ConvexVector,3> axes{{{1,0,0},{0,1,0},{0,0,1}}};
  const std::array<std::array<std::uint32_t,4>,6> face_indices{{{0,4,6,2},{1,3,7,5},{0,1,5,4},{2,6,7,3},{0,2,3,1},{4,5,7,6}}};
  std::array<ConvexFace,6> faces{};for(std::size_t i=0;i<6;i++)faces[i]={std::uint32_t(i/2),i%2!=0,face_indices[i]};
  const std::array<ConvexEdge,12> edges{{{0,1,0},{2,3,0},{4,5,0},{6,7,0},{0,2,1},{1,3,1},{4,6,1},{5,7,1},{0,4,2},{1,5,2},{2,6,2},{3,7,2}}};
  ConvexInstance first{{{cube,axes,axes},faces,edges},{},1},second=first;second.transform.translation={1.5f,0,0};
  if(collide_convex(first,second).contacts.size()!=4||select_edge(first.shape,0,{0,1,0})==no_convex_feature)return 22;
  first.transform.translation={0,.5f,0};
  if(collide_convex_mesh(first,{mesh_vertices,cooked,tree,{}},{{0,0,0},{1,1,1},0}).contacts.empty())return 23;
  std::array<ContactIsland,1> islands{};islands[0].static_normals.push_back(prepared.normal);
  solve_contact_islands(contact_body,coefficients,islands,{0,0,2});
  std::array<ConstraintIsland,1> with_joints{};
  with_joints[0].early_points.push_back({0,fixed_constraint_body,{},{},{1,0,0},0,1,.1f,0});
  solve_constraint_islands(contact_body,coefficients,with_joints,{0,0,1});
  solve_angular_constraints(contact_body,coefficients,{});solve_angular_couplings(contact_body,coefficients,{});
  ForceAccumulator auxiliary_force{};apply_local_force(auxiliary_force,{}, {1,2,3});
  apply_auxiliary_vehicle_forces(auxiliary_force,{}, {},{{5,0,10},1,0,0,0},{2,1,1,1},{},1);
  const auto grouped=build_contact_patches(collide_convex(first,second).contacts,SurfaceMaterialTable{},{},{},0x30abc000);
  if(grouped.empty())return 25;
  RigidMeshConfiguration scene_config{};scene_config.model.angular_speed_limit=100;scene_config.velocity.coefficients={.1f,.1f,.1f,1};scene_config.environment.attenuate_small_velocities=false;
  scene_config.velocity_iterations={4,1,4};scene_config.position={0,.1f,.2f};scene_config.position_iterations=4;scene_config.body_surface_id=1;
  RigidMeshWorld scene(first.shape,{{0,0,0},{1,1,1},0},mesh_vertices,indexed,{},scene_config);RigidState start{};start.position[1]=3;scene.reset(start);
  const auto checkpoint=scene.snapshot();ForceAccumulator no_force{};scene.step(.01f,no_force);scene.restore(checkpoint);
  if(scene.tick()!=0||auxiliary_force.linear!=std::array{1.f,2.f,3.f})return 24;
  WheelKinematicState wheel{};wheel.length=.1f;wheel.normal_44={0,1,0};wheel.contact_word_34=1;MeshTransform wheel_pose{};
  update_wheel_spin(wheel,{0,0,0,0,0,.5f,false,false,0,0,0xffffffffu,0},{100,-100,.5f,17},.01f);
  update_wheel_kinematics(wheel,wheel_pose,{{1,1,0},false,.5f,0,0,10},{2,.2f,.5f,10,.5f,20,3,false,false,{}},{},.01f);
  if(std::abs(wheel.length-.11f)>1e-6f)return 26;
  std::array<RigidState,1> joint_body{};std::array<float,3> vector{1,2,3};
  rotate_vector_quaternion(vector,{1,0,0,0});
  solve_projection_positions(joint_body,std::array<ProjectionPositionConstraint,1>{{{0,fixed_constraint_body,-1,{},{1,0,0}}}});
  solve_anchor_positions(joint_body,{});solve_quaternion_axes(joint_body,{});
  solve_position_islands(joint_body,coefficients,{},2,{0,.1f,.2f});
  shift_model_center_frame(joint_body,std::array<std::array<float,3>,1>{{{1,0,0}}},false);
  if(joint_body[0].position[0]!=2||vector!=std::array{1.f,2.f,3.f})return 27;
  if(fast_sin_cos(0).cosine!=1||vertical_response({0,0,0},{0,1,0,1})!=std::array{1.f,1.f})return 28;
  float direction_factor{};update_direction_factor(direction_factor,{1,0,0,0},{0,0,1},1,{1,0},.01f);
  const auto surface_blend=blend_wheel_surfaces({}, {}, {}, {},0,false,false);
  if(direction_factor!=1||surface_blend.curve_response!=std::array{1.f,1.f,1.f,0.f})return 29;
  ForceAccumulator resistance_force{};VehicleResistanceState resistance_state{};
  apply_local_torque(resistance_force,{}, {1,2,3});
  apply_vehicle_resistance(resistance_force,resistance_state,{}, {},{},0,0);
  if(resistance_force.angular!=std::array{1.f,2.f,3.f})return 30;
  RigidState fused_rotation{};correct_rotation(fused_rotation,{.1f,.2f,.3f},false,PositionMathPath::fused_avx_fma);
  if(!std::isfinite(fused_rotation.quaternion[0]))return 31;
  if(surface_material_name(16)!="Asphalt"||dataset_material_code(16)!=1||dataset_material_code(0)!=2||dataset_material_code(255)!=255)return 32;
  const auto step_parameters=prepare_step_parameters(.01f,{0,-9.81f,0},{},0x12345678,0x87654321);
  if(step_parameters.inverse_interval!=100.f||step_parameters.gravity_magnitude!=9.81f||step_parameters.opaque_24!=0x12345678||step_parameters.opaque_28!=0x87654321)return 33;
  std::array<BodyActivationState,1> activation{};const std::array<BodyActivationInput,1> activation_input{};
  prepare_body_activation(activation,activation_input,{});
  if(activation[0].coefficients[3]!=1.f||model_fixed_for_flags(1,8)||std::bit_cast<std::uint32_t>(native_vehicle_interval)!=0x3c23d70b)return 34;
  float surface_scalar=.5f;SurfaceScalarInput surface_input{};surface_input.wheel_contact_34[0]=1;
  SurfaceBlendValues surface_values{};surface_values.word_28=1000;const std::array<CurvePoint,1> recovery_curve{{{0,1}}};
  update_surface_scalar(surface_scalar,surface_input,surface_values,{recovery_curve,0},.01f);
  if(surface_scalar!=.49f||fast_asin(0)!=0||fast_acos(1)!=0||vehicle_steering_angle(0,1,{2,0},8,0)!=0)return 35;
  VehicleSubstepMotion scene_motion{{100,0,0},{},{},{}};
  const auto scene_plan=select_vehicle_substeps(scene_motion,1.f,1.f,native_vehicle_interval);
  if(scene_plan.substeps!=2||scene_plan.timestamp_subtrahend_nanoseconds>=0
     ||vehicle_last_substep_interval(scene_plan)!=native_vehicle_interval/2)return 36;
  std::cout << "PASS external C++20 consumer: SDK 0.26 + research scene substeps, mesh cooking/tree/collision, convex SAT, polygon contacts, curve/suspension force, prior solvers, native PPO trainer ABI 1, game ABI 3, policy ABI 1\n";
  return 0;
}

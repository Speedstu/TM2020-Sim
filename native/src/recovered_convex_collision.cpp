#include "tm2020/recovered_convex_collision.hpp"
#include "tm2020/recovered_polygon.hpp"
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
void bounded(const ConvexVector& p){for(float x:p)require(std::isfinite(x)&&std::abs(x)<=1e6f,"Convex contact exceeds finite domain");}
ConvexVector rotate(const MeshTransform& t,const ConvexVector& p){
    ConvexVector out{};for(std::size_t k=0;k<3;k++)out[k]=(p[0]*t.rotation[k*3]+p[1]*t.rotation[k*3+1])+p[2]*t.rotation[k*3+2];return out;
}
ConvexVector world(const MeshTransform& t,const ConvexVector& p){auto out=rotate(t,p);for(std::size_t k=0;k<3;k++)out[k]=out[k]+t.translation[k];return out;}
void valid(const ConvexInstance& instance){
    const auto& shape=instance.shape;require(!shape.faces.empty()&&!shape.edges.empty()&&!shape.axes.vertices.empty(),"Convex collision requires closed nonempty topology");
    require(shape.axes.vertices.size()<=4096&&shape.faces.size()<=4096&&shape.edges.size()<=16384&&shape.axes.face_normals.size()<=256&&shape.axes.edge_directions.size()<=256,"Convex collision exceeds topology domain");
    select_incident_face(shape,{1,0,0}); // Full shared topology/index validation.
    for(const auto& face:shape.faces)require(face.vertices.size()>=3&&face.vertices.size()<=4096,"Convex face loop count invalid");
    for(const auto& set:{shape.axes.face_normals,shape.axes.edge_directions})for(const auto& v:set){const float n=(v[0]*v[0]+v[1]*v[1])+v[2]*v[2];require(std::abs(n-1.f)<=2e-4f,"Convex directions must be unit length");}
    const auto& r=instance.transform.rotation;for(float x:r)require(std::isfinite(x)&&std::abs(x)<=1.0002f,"Convex transform rotation exceeds finite rigid domain");bounded(instance.transform.translation);
    for(std::size_t i=0;i<3;i++)for(std::size_t j=0;j<3;j++){
        const float product=(r[i*3]*r[j*3]+r[i*3+1]*r[j*3+1])+r[i*3+2]*r[j*3+2];require(std::abs(product-(i==j?1.f:0.f))<=2e-4f,"Convex transform rotation is not orthonormal");
    }
}
// 0x1844e0: separate positive and negative translation projections, then add.
// Computing R^T*(tB-tA) instead changes the original float rounding.
MeshTransform relative(const MeshTransform& a,const MeshTransform& b){
    MeshTransform out{};
    for(std::size_t row=0;row<3;row++)for(std::size_t col=0;col<3;col++)out.rotation[row*3+col]=(b.rotation[3+col]*a.rotation[3+row]+b.rotation[col]*a.rotation[row])+b.rotation[6+col]*a.rotation[6+row];
    for(std::size_t k=0;k<3;k++){
        const float positive=(b.translation[0]*a.rotation[k]+b.translation[1]*a.rotation[3+k])+b.translation[2]*a.rotation[6+k];
        const float negative=((-a.translation[0])*a.rotation[k]+(-a.translation[1])*a.rotation[3+k])+(-a.translation[2])*a.rotation[6+k];
        out.translation[k]=positive+negative;
    }
    return out;
}
MeshTransform inverse(const MeshTransform& input){
    MeshTransform out{};for(std::size_t i=0;i<3;i++)for(std::size_t j=0;j<3;j++)out.rotation[i*3+j]=input.rotation[j*3+i];
    const ConvexVector negative{-input.translation[0],-input.translation[1],-input.translation[2]};out.translation=rotate(out,negative);return out;
}
std::array<float,12> packed(const MeshTransform& t){std::array<float,12> out{};std::copy(t.rotation.begin(),t.rotation.end(),out.begin());std::copy(t.translation.begin(),t.translation.end(),out.begin()+9);return out;}
std::vector<ConvexVector> loop(const ConvexTopologyView& shape,std::uint32_t face){
    require(face<shape.faces.size(),"Convex face witness does not resolve");std::vector<ConvexVector> out;for(auto index:shape.faces[face].vertices)out.push_back(shape.axes.vertices[index]);return out;
}
EdgeFrame transformed(EdgeFrame frame,const MeshTransform& transform){frame.center=world(transform,frame.center);frame.direction=rotate(transform,frame.direction);return frame;}
struct TriangleData {
    std::array<ConvexVector,3> vertices{},directions{};std::array<ConvexVector,1> normals{};
    const std::array<std::uint32_t,3> indices{0,1,2};
    std::array<ConvexFace,1> faces{};
    const std::array<ConvexEdge,3> edges{{{0,1,0},{1,2,1},{2,0,2}}};
    TriangleData(const CookedMeshView& mesh,std::uint32_t index,const MeshTransform& transform){
        const auto& triangle=mesh.triangles[index];
        for(std::size_t i=0;i<3;i++)vertices[i]=world(transform,mesh.vertices[triangle.vertices[i]]);
        normals[0]=rotate(transform,triangle.normal);
        for(std::size_t i=0;i<3;i++)for(std::size_t k=0;k<3;k++)directions[i][k]=vertices[(i+1)%3][k]-vertices[i][k];
        faces[0]={0,true,indices};
    }
    TriangleData(const TriangleData&)=delete;
    ConvexTopologyView view()const{return {{vertices,normals,directions},faces,edges};}
};
}
ConvexCollision collide_convex(const ConvexInstance& a,const ConvexInstance& b,bool generate_contacts){
    valid(a);valid(b);const auto transform=relative(a.transform,b.transform);
    std::vector<ConvexVector> vertices,normals,directions;for(const auto& p:b.shape.axes.vertices)vertices.push_back(world(transform,p));for(const auto& p:b.shape.axes.face_normals)normals.push_back(rotate(transform,p));for(const auto& p:b.shape.axes.edge_directions)directions.push_back(rotate(transform,p));
    const auto sat=separating_axes(a.shape.axes,{vertices,normals,directions});ConvexCollision out{};out.overlap=sat.overlap;out.witness_kind=sat.kind;
    if(!out.overlap||!generate_contacts)return out;
    require(sat.has_witness,"Convex overlap has no usable axis");
    const ConvexVector negative{-sat.normal[0],-sat.normal[1],-sat.normal[2]};ConvexVector penetration{};
    for(std::size_t k=0;k<3;k++)penetration[k]=(-sat.depth)*negative[k];
    ConvexContact contact{};contact.penetration_vector=rotate(a.transform,penetration);
    const auto rotated_negative=rotate(a.transform,negative);for(std::size_t k=0;k<3;k++)contact.normal[k]=-rotated_negative[k];
    contact.surface_id_a=a.surface_id;contact.surface_id_b=b.surface_id;
    const ConvexVector in_b{
        (transform.rotation[3]*sat.normal[1]+transform.rotation[0]*sat.normal[0])+transform.rotation[6]*sat.normal[2],
        (transform.rotation[4]*sat.normal[1]+transform.rotation[1]*sat.normal[0])+transform.rotation[7]*sat.normal[2],
        (transform.rotation[5]*sat.normal[1]+transform.rotation[2]*sat.normal[0])+transform.rotation[8]*sat.normal[2]};
    if(sat.kind==0){
        const auto reference=select_face_from_normal(a.shape,sat.index_a,negative),incident=select_incident_face(b.shape,in_b);
        const auto& face=a.shape.faces[reference];const auto points=face_contacts(loop(b.shape,incident),loop(a.shape,reference),a.shape.axes.face_normals[face.normal_index],packed(inverse(transform)),face.keep_normal);
        for(const auto& point:points){contact.world_point=world(b.transform,point);out.contacts.push_back(contact);}
    }else if(sat.kind==1){
        const auto reference=select_face_from_normal(b.shape,sat.index_a,in_b),incident=select_incident_face(a.shape,negative);
        const auto& face=b.shape.faces[reference];const auto points=face_contacts(loop(a.shape,incident),loop(b.shape,reference),b.shape.axes.face_normals[face.normal_index],packed(transform),face.keep_normal);
        for(const auto& point:points){contact.world_point=world(a.transform,point);out.contacts.push_back(contact);}
    }else{
        const auto first=transformed(edge_frame(a.shape,select_edge(a.shape,sat.index_a,negative)),a.transform);
        const auto second=transformed(edge_frame(b.shape,select_edge(b.shape,sat.index_b,in_b)),b.transform);const auto pair=closest_edges(first,second);
        for(std::size_t k=0;k<3;k++)contact.world_point[k]=((second.center[k]+second.direction[k]*pair.parameter_b)+(first.direction[k]*pair.parameter_a+first.center[k]))*.5f;
        out.contacts.push_back(contact);
    }
    for(const auto& c:out.contacts){bounded(c.penetration_vector);bounded(c.normal);bounded(c.world_point);}return out;
}
ConvexMeshCollision collide_convex_mesh(const ConvexInstance& a,const CookedMeshView& mesh,const AabbPrimitive& bounds,bool generate_contacts){
    valid(a);bounded(bounds.center);bounded(bounds.half_extent);for(float x:bounds.half_extent)require(x>=0,"Negative convex query half extent");
    require(mesh.vertices.size()<=1000000&&mesh.triangles.size()<=1000000,"Too much convex mesh geometry");
    for(const auto& p:mesh.vertices)bounded(p);
    for(const auto& triangle:mesh.triangles){bounded(triangle.normal);for(auto index:triangle.vertices)require(index<mesh.vertices.size(),"Convex mesh triangle vertex out of range");}
    for(const auto& node:mesh.tree)if(node.packed&1)require((node.packed>>1)<mesh.triangles.size(),"Convex mesh leaf out of range");
    for(float x:mesh.transform.rotation)require(std::isfinite(x)&&std::abs(x)<=1.0002f,"Invalid mesh rigid transform");
    bounded(mesh.transform.translation);
    const auto to_mesh=relative(mesh.transform,a.transform),to_a=inverse(to_mesh);
    const auto center=world(to_mesh,bounds.center);ConvexVector half{};
    for(std::size_t k=0;k<3;k++)half[k]=(std::abs(to_mesh.rotation[k*3])*bounds.half_extent[0]+std::abs(to_mesh.rotation[k*3+1])*bounds.half_extent[1])+std::abs(to_mesh.rotation[k*3+2])*bounds.half_extent[2];
    const auto leaves=query_aabb_tree(mesh.tree,center,half);ConvexMeshCollision out{};
    struct Candidate {std::uint32_t triangle{};SeparatingAxisResult axis;};std::vector<Candidate> candidates;
    for(auto leaf:leaves){
        const auto index=mesh.tree[leaf].packed>>1;const TriangleData triangle(mesh,index,to_a);
        const auto sat=separating_axes(a.shape.axes,triangle.view().axes,9.999999747378752e-5f);
        if(!sat.overlap)continue;
        out.overlap=true;if(!generate_contacts)return out;
        if(candidates.size()==128)break;
        candidates.push_back({index,sat});
    }
    for(const auto& candidate:candidates){
        const auto& sat=candidate.axis;require(sat.has_witness,"Convex mesh overlap has no usable axis");
        const TriangleData triangle(mesh,candidate.triangle,{});const auto shape=triangle.view();
        const ConvexVector negative{-sat.normal[0],-sat.normal[1],-sat.normal[2]};const auto rotated=rotate(a.transform,negative);
        ConvexContact contact{};for(std::size_t k=0;k<3;k++){contact.normal[k]=-rotated[k];contact.penetration_vector[k]=sat.depth*contact.normal[k];}
        contact.surface_id_a=a.surface_id;contact.surface_id_b=mesh.triangles[candidate.triangle].surface_id;
        if(sat.kind==1){
            const auto incident=select_incident_face(a.shape,negative);
            const auto points=face_contacts(loop(a.shape,incident),loop(shape,0),triangle.normals[0],packed(to_a),true);
            for(const auto& point:points){contact.world_point=world(a.transform,point);out.contacts.push_back(contact);}
        }else if(sat.kind==0){
            const auto reference=select_face_from_normal(a.shape,sat.index_a,negative);const auto& face=a.shape.faces[reference];
            const auto points=face_contacts(loop(shape,0),loop(a.shape,reference),a.shape.axes.face_normals[face.normal_index],packed(to_mesh),face.keep_normal);
            for(const auto& point:points){contact.world_point=world(mesh.transform,point);out.contacts.push_back(contact);}
        }else{
            const auto normal_mesh=rotate(to_mesh,sat.normal);
            const auto first=transformed(edge_frame(a.shape,select_edge(a.shape,sat.index_a,negative)),a.transform);
            const auto second=transformed(edge_frame(shape,select_edge(shape,sat.index_b,normal_mesh)),mesh.transform);const auto pair=closest_edges(first,second);
            for(std::size_t k=0;k<3;k++)contact.world_point[k]=((second.direction[k]*pair.parameter_b+second.center[k])+(first.direction[k]*pair.parameter_a+first.center[k]))*.5f;
            out.contacts.push_back(contact);
        }
    }
    for(const auto& contact:out.contacts){bounded(contact.normal);bounded(contact.penetration_vector);bounded(contact.world_point);}return out;
}
}

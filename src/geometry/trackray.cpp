// Trackmania 2020 research: deterministic CPU triangle BVH raycaster.
// Operates on explicitly supplied OBJ/.tmcol triangles; capture metadata records
// source coverage. This does not assert complete original-game collision fidelity.
// No dependencies beyond the existing C++20 compiler. No game-process access.
#include <algorithm>
#include <array>
#include <bit>
#include <cstring>
#include <filesystem>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

struct Vec {
    double x=0,y=0,z=0;
    double& operator[](int a) {return a==0?x:a==1?y:z;}
    double operator[](int a) const{return a==0?x:a==1?y:z;}
};
static Vec operator+(Vec a,Vec b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
static Vec operator-(Vec a,Vec b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
static Vec operator*(Vec a,double f){return {a.x*f,a.y*f,a.z*f};}
static Vec operator/(Vec a,double f){return a*(1.0/f);}
static double dot(Vec a,Vec b){return a.x*b.x+a.y*b.y+a.z*b.z;}
static Vec cross(Vec a,Vec b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
static double norm(Vec a){return std::sqrt(dot(a,a));}
static Vec unit(Vec a){double n=norm(a);return n>1e-15?a/n:Vec{0,1,0};}
static Vec vmin(Vec a,Vec b){return {std::min(a.x,b.x),std::min(a.y,b.y),std::min(a.z,b.z)};}
static Vec vmax(Vec a,Vec b){return {std::max(a.x,b.x),std::max(a.y,b.y),std::max(a.z,b.z)};}
struct Box { Vec lo{1e300,1e300,1e300}, hi{-1e300,-1e300,-1e300}; };
static void grow(Box& b,Vec x){b.lo=vmin(b.lo,x);b.hi=vmax(b.hi,x);}
struct Tri {Vec a,b,c,n,mid;Box box;};
struct Node {Box box;int left=-1,right=-1,start=0,end=0;};
struct Hit {bool ok=false;double t=0;Vec pos,n;int index=-1;};

class BVH {
    std::vector<Tri> tris;
    std::vector<int> index;
    std::vector<Node> nodes;

    int build(int start,int end) {
        Node node;node.start=start;node.end=end;
        Box centers;
        for(int i=start;i<end;++i) {
            const Tri& tri=tris[index[i]];
            grow(node.box,tri.box.lo);grow(node.box,tri.box.hi);grow(centers,tri.mid);
        }
        int here=(int)nodes.size();
        nodes.push_back(node);
        if(end-start<=8)return here;
        Vec extent=centers.hi-centers.lo;
        int axis=extent.y>extent.x?1:0;
        if(extent.z>extent[axis])axis=2;
        if(extent[axis]<1e-10)return here;
        int middle=(start+end)/2;
        std::nth_element(index.begin()+start,index.begin()+middle,index.begin()+end,
                         [&](int a,int b){return tris[a].mid[axis]<tris[b].mid[axis];});
        int left=build(start,middle);
        int right=build(middle,end);
        nodes[here].left=left;nodes[here].right=right;
        return here;
    }

    static bool boxHit(const Box& b,Vec p,Vec d,double upper) {
        double lower=0.0;
        for(int axis=0;axis<3;++axis) {
            double v=d[axis];
            if(std::abs(v)<1e-14) {
                if(p[axis]<b.lo[axis] || p[axis]>b.hi[axis])return false;
            } else {
                double a=(b.lo[axis]-p[axis])/v;
                double z=(b.hi[axis]-p[axis])/v;
                if(a>z)std::swap(a,z);
                lower=std::max(lower,a);
                upper=std::min(upper,z);
                if(lower>upper)return false;
            }
        }
        return true;
    }

    static bool triangleHit(const Tri& t,Vec p,Vec d,double maxDist,double& hitT) {
        Vec e1=t.b-t.a,e2=t.c-t.a;
        Vec crossD=cross(d,e2);
        double det=dot(e1,crossD);
        if(std::abs(det)<1e-13)return false;
        double inv=1.0/det;
        Vec v=p-t.a;
        double u=dot(v,crossD)*inv;
        if(u<-1e-11 || u>1+1e-11)return false;
        Vec q=cross(v,e1);
        double w=dot(d,q)*inv;
        if(w<-1e-11 || u+w>1+1e-11)return false;
        double distance=dot(e2,q)*inv;
        if(distance<1e-8 || distance>maxDist)return false;
        hitT=distance;
        return true;
    }
public:
    explicit BVH(std::vector<Tri> t):tris(std::move(t)){
        index.resize(tris.size());std::iota(index.begin(),index.end(),0);
        nodes.reserve(tris.size()/3+10);
        if(!tris.empty())build(0,(int)index.size());
    }
    size_t triangleCount()const{return tris.size();}
    size_t nodeCount()const{return nodes.size();}
    const Tri& triangle(size_t k)const{return tris.at(k);}
    Hit cast(Vec start,Vec direction,double maxDist=1e6)const{
        Hit best;best.t=maxDist;
        direction=unit(direction);
        if(nodes.empty())return best;
        std::array<int,96> stack{};int count=0;
        stack[count++]=0;
        while(count){
            int which=stack[--count];const Node& n=nodes[which];
            if(!boxHit(n.box,start,direction,best.t))continue;
            if(n.left==-1) {
                for(int i=n.start;i<n.end;++i) {
                    int id=index[i];double t=0;
                    if(triangleHit(tris[id],start,direction,best.t,t)){
                        best.ok=true;best.t=t;best.index=id;
                        best.n=tris[id].n;best.pos=start+direction*t;
                    }
                }
            }else{
                if(count+2>(int)stack.size())throw std::runtime_error("BVH stack overflow");
                stack[count++]=n.left;stack[count++]=n.right;
            }
        }
        return best;
    }
};

static std::vector<Tri> load(const std::string& path) {
    std::ifstream f(path);
    if(!f)throw std::runtime_error("Cannot read OBJ: "+path);
    std::vector<Vec> vertices;
    std::vector<Tri> triangles;
    std::string line;
    while(std::getline(f,line)){
        if(line.size()<2)continue;
        if(line[0]=='v' && line[1]==' '){
            std::istringstream s(line.substr(2));Vec p;
            if(s>>p.x>>p.y>>p.z)vertices.push_back(p);
        } else if(line[0]=='f' && line[1]==' '){
            std::istringstream s(line.substr(2));std::string a,b,c;
            if(!(s>>a>>b>>c))continue;
            auto ix=[&](std::string field)->size_t{
                auto pos=field.find('/');
                long long v=std::stoll(field.substr(0,pos));
                if(v<=0 || v>(long long)vertices.size())throw std::runtime_error("Bad OBJ index");
                return (size_t)(v-1);
            };
            Vec va=vertices[ix(a)],vb=vertices[ix(b)],vc=vertices[ix(c)];
            Vec normal=cross(vb-va,vc-va);
            if(norm(normal)<1e-12)continue;
            Tri t;t.a=va;t.b=vb;t.c=vc;t.n=unit(normal);
            t.mid=(va+vb+vc)/3.0;
            grow(t.box,va);grow(t.box,vb);grow(t.box,vc);
            triangles.push_back(t);
        }
    }
    if(triangles.empty())throw std::runtime_error("No valid triangles in OBJ");
    return triangles;
}

// Fast portable-on-x64 binary triangle representation (NOT packed BVH nodes).
// .tmcol v1 contains only non-degenerate triangles in stable OBJ parsing order.
// No native Stadium game package assets are redistributed.
#ifndef TRACKRAY_LIBRARY
static void saveCache(const std::string& filename,const std::vector<Tri>& data){
    if(std::endian::native != std::endian::little)
        throw std::runtime_error("Only little-endian binary geometry supported");
    if(data.size()>5'000'000)throw std::runtime_error("Too many triangles in cache");
    std::ofstream f(filename,std::ios::binary|std::ios::trunc);
    if(!f)throw std::runtime_error("Could not create cache "+filename);
    const char magic[8]={'T','M','C','O','L','0','1','\0'};
    f.write(magic,8);
    std::uint32_t n=(std::uint32_t)data.size();
    f.write(reinterpret_cast<const char*>(&n),sizeof(n));
    for(const auto& t:data) {
        const double coords[9]{t.a.x,t.a.y,t.a.z,t.b.x,t.b.y,t.b.z,t.c.x,t.c.y,t.c.z};
        f.write(reinterpret_cast<const char*>(coords),sizeof(coords));
    }
    if(!f)throw std::runtime_error("Failed writing tmcol cache");
}
#endif // TRACKRAY_LIBRARY
static std::vector<Tri> loadCache(const std::string& filename){
    if(std::endian::native != std::endian::little)
        throw std::runtime_error("Only little-endian binary geometry supported");
    std::ifstream f(filename,std::ios::binary|std::ios::ate);
    if(!f)throw std::runtime_error("Could not open tmcol cache");
    const auto size=f.tellg();
    if(size<12)throw std::runtime_error("tmcol too short");
    f.seekg(0);
    char magic[8]{};
    f.read(magic,8);
    if(!f || std::memcmp(magic,"TMCOL01\0",8)!=0)
        throw std::runtime_error("Invalid tmcol magic/version");
    std::uint32_t n{};
    f.read(reinterpret_cast<char*>(&n),4);
    if(n<1||n>5'000'000u||size!=(std::streamoff)(12ull+(std::uint64_t)n*72ull))
        throw std::runtime_error("Invalid tmcol count/size");
    std::vector<Tri> out;
    out.reserve(n);
    for(std::uint32_t i=0;i<n;i++){
        double v[9]{};
        if(!f.read(reinterpret_cast<char*>(v),sizeof(v)))
            throw std::runtime_error("Truncated tmcol");
        for(double x:v)if(!std::isfinite(x))
            throw std::runtime_error("Nonfinite tmcol coordinate");
        Tri t;t.a={v[0],v[1],v[2]};t.b={v[3],v[4],v[5]};t.c={v[6],v[7],v[8]};
        Vec normal=cross(t.b-t.a,t.c-t.a);
        if(norm(normal)<1e-12)throw std::runtime_error("Degenerate cached triangle");
        t.n=unit(normal);
        t.mid=(t.a+t.b+t.c)/3.;
        grow(t.box,t.a);grow(t.box,t.b);grow(t.box,t.c);
        out.push_back(t);
    }
    return out;
}
static std::vector<Tri> loadAny(const std::string& filename){
    return std::filesystem::path(filename).extension()==".tmcol"?
        loadCache(filename):load(filename);
}

#ifndef TRACKRAY_LIBRARY
static void printHit(Hit h){
    std::cout<<std::setprecision(12);
    if(!h.ok){std::cout<<"{\"hit\":false}\n";return;}
    std::cout<<"{\"hit\":true,\"distance\":"<<h.t<<",\"triangle\":"<<h.index
        <<",\"position\":["<<h.pos.x<<","<<h.pos.y<<","<<h.pos.z
        <<"],\"normal\":["<<h.n.x<<","<<h.n.y<<","<<h.n.z<<"]}\n";
}
#endif // TRACKRAY_LIBRARY
#ifdef _WIN32
#define TM_EXPORT __declspec(dllexport)
#else
#define TM_EXPORT __attribute__((visibility("default")))
#endif
static thread_local std::string apiError;
extern "C" {
TM_EXPORT void* tm_world_open(const char* filename) noexcept {
    try {
        apiError.clear();
        if(!filename || !filename[0])throw std::runtime_error("Empty collision mesh filename");
        return new BVH(loadAny(filename));
    }catch(const std::exception& e){
        apiError=e.what();
        return nullptr;
    }
}
TM_EXPORT void tm_world_close(void* world) noexcept {
    delete static_cast<BVH*>(world);
}
TM_EXPORT const char* tm_last_error() noexcept {
    return apiError.c_str();
}
TM_EXPORT long long tm_world_triangle_count(const void* world) noexcept {
    if(!world)return -1;
    return (long long)static_cast<const BVH*>(world)->triangleCount();
}
// inputs: [ox,oy,oz, dx,dy,dz, max_distance] for each ray
// output: [hit (0/1),distance, px,py,pz,nx,ny,nz, triangleIndex]
TM_EXPORT int tm_world_cast_batch(const void* world, const double* rays,
    long long count, double* results) noexcept {
    if(!world || !rays || !results || count<0 || count>10000000)return -1;
    try {
        apiError.clear();
        auto* w=static_cast<const BVH*>(world);
        for(long long i=0;i<count;i++){
            auto* ray=rays+7*i;
            auto* output=results+9*i;
            Vec origin{ray[0],ray[1],ray[2]};
            Vec direction{ray[3],ray[4],ray[5]};
            if(!std::isfinite(dot(origin,origin)) ||
               !std::isfinite(dot(direction,direction)) ||
               norm(direction)<1e-12 || !std::isfinite(ray[6]) || ray[6]<=0) {
                throw std::runtime_error("Invalid ray input: nonfinite/zero direction/invalid max distance");
            }
            Hit hit=w->cast(origin,direction,ray[6]);
            output[0]=hit.ok ? 1 : 0;
            output[1]=hit.ok ? hit.t : std::numeric_limits<double>::quiet_NaN();
            output[2]=hit.ok ? hit.pos.x : std::numeric_limits<double>::quiet_NaN();
            output[3]=hit.ok ? hit.pos.y : std::numeric_limits<double>::quiet_NaN();
            output[4]=hit.ok ? hit.pos.z : std::numeric_limits<double>::quiet_NaN();
            output[5]=hit.ok ? hit.n.x : std::numeric_limits<double>::quiet_NaN();
            output[6]=hit.ok ? hit.n.y : std::numeric_limits<double>::quiet_NaN();
            output[7]=hit.ok ? hit.n.z : std::numeric_limits<double>::quiet_NaN();
            output[8]=hit.ok ? hit.index : -1;
        }
        return 0;
    }catch(const std::exception& e) {
        apiError=e.what();
        return -2;
    }
}
}
#ifndef TRACKRAY_LIBRARY
int main(int argc,char** argv) {
    try {
        if(argc<4) {
            std::cerr<<"Usage: trackray <mesh.obj> --probe x y z dx dy dz [maxDistance]\n"
                <<"       trackray <mesh.obj> --bench <N>\n"
                <<"       trackray <mesh.obj> --verify <N>\n"
                <<"       trackray <mesh.obj> --batch <rays.txt>\n"
                <<"       trackray <mesh.obj> --cache <output.tmcol>\n";return 2;
        }
        std::string cmd=argv[2];
        if(cmd=="--cache"){
            if(argc<4)throw std::runtime_error("--cache requires output.tmcol filename");
            if(std::filesystem::path(argv[1]).extension()==".tmcol")
                throw std::runtime_error("Refusing binary-to-binary cache");
            const auto tris=load(argv[1]);
            saveCache(argv[3],tris);
            std::cout<<"CACHED triangles="<<tris.size()<<" output="<<argv[3]<<"\n";
            return 0;
        }
        auto time=std::chrono::steady_clock::now();
        BVH ray(loadAny(argv[1]));
        double buildMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-time).count();
        if(cmd=="--batch"){
            std::ifstream rays(argv[3]);
            if(!rays)throw std::runtime_error("Cannot open batch ray input");
            std::string line;
            while(std::getline(rays,line)){
                if(line.empty() || line[0]=='#')continue;
                std::istringstream stream(line);
                Vec p,d;double dist=1e6;
                if(!(stream>>p.x>>p.y>>p.z>>d.x>>d.y>>d.z))
                    throw std::runtime_error("Invalid batch line: "+line);
                if(stream>>dist){}
                if(norm(d)<1e-12)throw std::runtime_error("Zero batch ray direction");
                printHit(ray.cast(p,d,dist));
            }
        }else if(cmd=="--probe"){
            if(argc<9)throw std::runtime_error("Expected ray origin + direction (6 numbers)");
            Vec p{std::stod(argv[3]),std::stod(argv[4]),std::stod(argv[5])};
            Vec d{std::stod(argv[6]),std::stod(argv[7]),std::stod(argv[8])};
            if(norm(d)<1e-12)throw std::runtime_error("Zero direction");
            double maxDist=argc>=10?std::stod(argv[9]):1e6;
            printHit(ray.cast(p,d,maxDist));
        }else if(cmd=="--bench"||cmd=="--verify"){
            int n=std::stoi(argv[3]);if(n<1||n>1000000)throw std::runtime_error("Invalid iterations");
            std::mt19937 rng(421);
            std::uniform_int_distribution<int> pick(0,(int)ray.triangleCount()-1);
            int ok=0;double total=0;
            auto start=std::chrono::steady_clock::now();
            for(int i=0;i<n;++i) {
                Tri tri=ray.triangle(pick(rng));
                Vec origin=tri.mid+tri.n*0.1;
                Hit result=ray.cast(origin,tri.n*(-1),1.0);
                if(result.ok) {++ok;total+=result.t;}
            }
            double secs=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
            std::cout<<std::fixed<<std::setprecision(6)
               <<"{\"triangles\":"<<ray.triangleCount()<<",\"nodes\":"<<ray.nodeCount()
               <<",\"buildMs\":"<<buildMs<<",\"rays\":"<<n
               <<",\"hits\":"<<ok<<",\"hitRatio\":"<<(double)ok/n
               <<",\"raysPerSecond\":"<<(double)n/secs
               <<",\"meanHitDistance\":"<<(ok?total/ok:0)<<"}\n";
            if(cmd=="--verify" && ok<n/2)return 1;
        }else {throw std::runtime_error("Unknown operation");}
        return 0;
    } catch (const std::exception& e) {
        std::cerr<<"error: "<<e.what()<<"\n";return 1;
    }
}
#endif // TRACKRAY_LIBRARY

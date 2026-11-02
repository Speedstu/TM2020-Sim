#define TM2020_POLICY_BUILD
#include "tm2020/policy.h"
#include "tm2020/rl.hpp"
#include <algorithm>
#include <memory>
#include <string>
#include <cstring>
namespace {
struct Model {
    std::string schema;
    tm2020::rl::ActorCritic policy;
    explicit Model(const char* path):policy(tm2020::rl::ActorCritic::load(
        std::filesystem::path(std::u8string(reinterpret_cast<const char8_t*>(path),std::strlen(path))),&schema)){}
};
thread_local std::string error;
}
extern "C" {
uint32_t tm2020_policy_version(void){return TM2020_POLICY_API_VERSION;}
#ifdef _WIN32
uint32_t __stdcall tm2020_policy_host_probe(void* reserved){return reserved?0:TM2020_POLICY_API_VERSION;}
#endif
const char* tm2020_policy_last_error(void){return error.c_str();}
int32_t tm2020_policy_open(const char* path,tm2020_policy_handle* out){
    if(!out){error="Null output handle";return -1;}
    *out=nullptr;
    if(!path||!*path){error="Missing model path";return -1;}
    try{auto model=std::make_unique<Model>(path);*out=model.release();error.clear();return 0;}
    catch(const std::exception& e){error=e.what();return -2;}
    catch(...){error="Unknown policy load error";return -2;}
}
int32_t tm2020_policy_get_info(tm2020_policy_handle h,tm2020_policy_info* out){
    if(!h||!out||out->size_bytes!=sizeof(*out)||out->api_version!=TM2020_POLICY_API_VERSION){error="Invalid policy info arguments";return -1;}
    const auto& p=static_cast<Model*>(h)->policy;
    *out={sizeof(*out),TM2020_POLICY_API_VERSION,static_cast<uint32_t>(p.actor.inputs),static_cast<uint32_t>(p.actor.outputs),static_cast<uint32_t>(p.actor.hidden),0};
    error.clear();return 0;
}
const char* tm2020_policy_schema(tm2020_policy_handle h){if(!h){error="Null policy handle";return nullptr;}error.clear();return static_cast<Model*>(h)->schema.c_str();}
int32_t tm2020_policy_predict(tm2020_policy_handle h,const double* x,uint32_t nx,double* a,uint32_t na,double* v){
    // Bound clearing by the actual model dimension; malformed size arguments
    // must not cause an out-of-bounds memset before validation.
    if(!h||!x||!a||!v){error="Null policy prediction argument";return -1;}
    const auto& p=static_cast<Model*>(h)->policy;
    if(nx!=p.actor.inputs||na!=p.actor.outputs){error="Policy dimension mismatch";return -1;}
    std::fill(a,a+na,0.);*v=0;
    try{p.predict_into(std::span(x,nx),std::span(a,na),*v);error.clear();return 0;}
    catch(const std::exception& e){std::fill(a,a+na,0.);*v=0;error=e.what();return -2;}
    catch(...){std::fill(a,a+na,0.);*v=0;error="Unknown policy prediction error";return -2;}
}
void tm2020_policy_close(tm2020_policy_handle h){delete static_cast<Model*>(h);}
}

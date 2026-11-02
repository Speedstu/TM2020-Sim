#include "tm2020/recovered_activation.hpp"
#include "owned_arithmetic_image.hpp"
#include <bit>
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T,std::size_t N>void put(std::array<std::byte,N>& block,std::size_t offset,const T& value){
    check(offset+sizeof(T)<=N,"Wake fixture overflow");std::memcpy(block.data()+offset,&value,sizeof(T));
}
struct Queue {std::uint32_t* data{};std::uint32_t count{},capacity{12};};
void word(std::ostream& out,std::uint32_t value){out.write(reinterpret_cast<const char*>(&value),4);}
void states(std::ostream& out,const std::array<WakeIndexState,8>& values){
    for(const auto& v:values){word(out,v.rest_since);word(out,std::uint32_t(v.active_index)|(std::uint32_t(v.reserved)<<16)|(std::uint32_t(v.queued)<<24));}
}
int main(int argc,char**argv)try{
    check(argc==3,"wake_queue_oracle original.exe new_output_dir");
    const std::filesystem::path folder(argv[2]);check(!std::filesystem::exists(folder),"Never overwrite wake evidence");
    std::filesystem::create_directories(folder);
    const std::array<std::array<unsigned,2>,3> ranges{{{0x7b9b70,0x7b9bd6},{0x13a3f00,0x13a3f17},{0x1dc0a0,0x1dc0e7}}};
    ArithmeticImage image(argv[1],ranges);using Fn=void(*)(void*,std::uint32_t);
    const auto original=reinterpret_cast<Fn>(image.base+0x7b9b70);
    std::ofstream output(folder/"wake-queue.cases",std::ios::binary);output.write("TMWAK001",8);word(output,20000);
    std::mt19937_64 rng(0x2026102902);std::uint64_t additions{},requests{};
    for(std::size_t case_id=0;case_id<20000;case_id++){
        const bool enabled=case_id%5!=0;
        std::array<WakeIndexState,8> native{},ported{};std::array<std::uint32_t,24> mapping{};
        std::array<std::uint32_t,8> reverse{};std::array<std::uint32_t,12> storage{};std::array<std::uint32_t,32> plan{};
        for(unsigned i=0;i<8;i++){
            native[i]={std::uint32_t(rng()),std::uint16_t(rng()%3==0?0xffff:rng()%16),std::uint8_t(rng()),std::uint8_t(rng()%3)};
            reverse[i]=std::uint32_t(rng());mapping[8+i]=reverse[i];mapping[i]=std::uint32_t(rng());
        }
        ported=native;for(auto& value:storage)value=std::uint32_t(rng());for(auto& value:plan)value=std::uint32_t(rng()%8);
        Queue queue{storage.data(),std::uint32_t(rng()%5),12};std::vector<std::uint32_t> pending(storage.begin(),storage.begin()+queue.count);
        std::array<std::byte,0x118> manager{};
        put(manager,0x90,native.data());put(manager,0xb0,mapping.data());put(manager,0xc0,std::uint32_t(8));
        put(manager,0x100,std::uintptr_t(enabled?1:0));put(manager,0x108,queue);
        word(output,enabled);states(output,native);for(auto value:reverse)word(output,value);
        word(output,queue.count);for(auto value:storage)word(output,value);for(auto value:plan)word(output,value);
        for(auto slot:plan){
            original(manager.data(),slot);const auto added=enqueue_body_wake(enabled,slot,ported,reverse,pending);
            additions+=added;requests++;
            std::memcpy(&queue,manager.data()+0x108,sizeof(queue));
            check(std::memcmp(native.data(),ported.data(),sizeof(native))==0,"Wake index bytes differ from original");
            check(queue.count==pending.size()&&std::equal(pending.begin(),pending.end(),storage.begin()),"Wake queue order/handle mapping differs");
        }
        states(output,native);word(output,queue.count);for(auto value:storage)word(output,value);
    }
    output.flush();check(bool(output),"Cannot save numeric wake cases");
    std::ofstream report(folder/"report.json");report<<"{\"schema\":\"tm2020_original_wake_enqueue_oracle_v1\",\"exeSha256\":\""<<executable_sha256
        <<"\",\"cases\":20000,\"requests\":"<<requests<<",\"queueAdditions\":"<<additions
        <<",\"cppIndexBytesAndLogicalQueueBitExact\":true,\"nativeHeapGrowthExercised\":false,\"activationCallbackExercised\":false,\"sourceGameProcessAccessed\":false,\"completeExactSimulatorQualified\":false}\n";
    check(bool(report),"Cannot write wake report");std::cout<<"PASS WAKE_ENQUEUE requests="<<requests<<" additions="<<additions<<'\n';
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}

// SPDX-License-Identifier: GPL-3.0-or-later
// Preserve the SDK's checksum and libstdc++ mt19937_64 shuffle at GPU migration.
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <locale>
#include <numeric>
#include <random>
#include <sstream>
#include <vector>
extern "C" uint64_t tmppo_checksum(const void* p,size_t n){
 const auto* b=static_cast<const unsigned char*>(p);uint64_t h=14695981039346656037ULL;
 for(size_t i=0;i<n;i++){h^=b[i];h*=1099511628211ULL;}return h;
}
extern "C" int tmppo_shuffle(const char* state,uint32_t* order,uint32_t n,char* next,size_t capacity){
 try{
  if(!state||!order||!next||!n||n>131072)return -1;
  std::istringstream in(state);in.imbue(std::locale::classic());std::mt19937_64 rng;
  if(!(in>>rng))return -1;
  std::vector<size_t> permutation(n);std::iota(permutation.begin(),permutation.end(),0);
  // The caller supplies the order from the previous epoch, exactly as the SDK.
  std::vector<bool> used(n);
  for(uint32_t i=0;i<n;i++){if(order[i]>=n||used[order[i]])return -1;used[order[i]]=true;permutation[i]=order[i];}
  std::shuffle(permutation.begin(),permutation.end(),rng);
  std::ostringstream out;out.imbue(std::locale::classic());out<<rng;auto text=out.str();
  if(text.size()+1>capacity)return -1;
  for(uint32_t i=0;i<n;i++)order[i]=static_cast<uint32_t>(permutation[i]);
  std::memcpy(next,text.c_str(),text.size()+1);return static_cast<int>(text.size());
 }catch(...){return -1;}
}

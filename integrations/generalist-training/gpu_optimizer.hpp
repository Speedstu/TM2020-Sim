// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "tm2020/rl.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <thread>
inline tm2020::rl::UpdateMetrics gpu_update(const std::filesystem::path& service,size_t sequence,
 const std::filesystem::path& input,const std::filesystem::path& rollout,size_t environments,
 const std::filesystem::path& output,const std::filesystem::path& metrics){
 namespace fs=std::filesystem;
 const auto request=service/("request-"+std::to_string(sequence)+".txt");
 const auto response=service/("response-"+std::to_string(sequence)+".txt");
 if(fs::exists(request)||fs::exists(response))throw std::runtime_error("GPU update request already exists");
 auto temporary=request;temporary+=".tmp";
 {std::ofstream file(temporary);file<<"TM2020_GPU_UPDATE_V1\n"<<sequence<<'\n'<<fs::absolute(input).string()<<'\n'
  <<fs::absolute(rollout).string()<<'\n'<<environments<<'\n'<<fs::absolute(output).string()<<'\n'<<fs::absolute(metrics).string()<<'\n';
  file.flush();if(!file)throw std::runtime_error("GPU request write failed");}
 fs::rename(temporary,request);
 const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(120);
 while(!fs::exists(response)){
  if(std::chrono::steady_clock::now()>deadline)throw std::runtime_error("CUDA optimizer timeout; previous complete checkpoint retained");
  std::this_thread::sleep_for(std::chrono::milliseconds(5));
 }
 std::ifstream in(response);std::string tag;size_t seq{};int result{};in>>tag>>seq>>result;
 if(!in||tag!="TM2020_GPU_UPDATE_RESULT_V1"||seq!=sequence)throw std::runtime_error("Invalid CUDA response");
 if(result){std::string message;std::getline(in>>std::ws,message);throw std::runtime_error("CUDA optimizer: "+message);}
 tm2020::rl::UpdateMetrics value{};
 in>>value.policy_loss>>value.value_loss>>value.approx_kl>>value.gradient_norm>>value.clip_fraction>>value.minibatches>>value.epochs>>value.kl_stopped;
 if(!in)throw std::runtime_error("Invalid CUDA optimizer metrics");return value;
}

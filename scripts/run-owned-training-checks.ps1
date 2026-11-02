param([switch]$SkipPhysicsReplay)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$exe='D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe'
$guard=Join-Path $root 'native/build/libtm2020_owned_unicorn_guard.dll'
$policy=Join-Path $root 'native/build/libtm2020_policy.dll'
$fixture=Join-Path $root 'local/recon/rest-history-training-canonical-v5/owned_control_schedule.tmstep'
$recon=Join-Path $root 'local/recon'
function Assert-TrainingExit([string]$message){if($LASTEXITCODE -ne 0){throw $message}}
cmake --build (Join-Path $root 'native/build') -j 4
Assert-TrainingExit 'Native build failed'
ctest --test-dir (Join-Path $root 'native/build') --output-on-failure
Assert-TrainingExit 'Native checks failed'
python (Join-Path $PSScriptRoot 'test_owned_native_guard.py') --dll $guard --report (Join-Path $recon 'owned-native-guard-adversarial.json')
Assert-TrainingExit 'Compiled guard checks failed'
if(!$SkipPhysicsReplay){
 python (Join-Path $PSScriptRoot 'replay_original_step.py') --fixtures $fixture --exe $exe --native-guard $guard --initialize-writes --report (Join-Path $recon 'owned-training-final-reference.json')
 Assert-TrainingExit 'Final observed-input reference differs'
 foreach($suffix in @('','-resume')){
  python (Join-Path $PSScriptRoot 'audit_owned_ppo_rollout.py') --run (Join-Path $recon ('owned-ppo-rest-history-canonical-v5'+$suffix)) --fixture $fixture --exe $exe --native-guard $guard --policy-dll $policy --report (Join-Path $recon ('owned-ppo-canonical-v5'+$suffix+'-physics-audit.json'))
  Assert-TrainingExit 'PPO accepted physics history differs'
 }
}
python (Join-Path $PSScriptRoot 'audit_owned_training.py')
Assert-TrainingExit 'Owned training evidence audit failed'

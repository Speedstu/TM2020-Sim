param([switch]$SkipBuild,[switch]$SkipOffline)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $root 'native\build'
$exe='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'
$recon=Join-Path $root 'local\recon'
function Assert-OwnedExit([string]$message){if($LASTEXITCODE -ne 0){throw $message}}
if(!$SkipBuild){
 & cmake --build $build --target tm2020_original_step_native tm2020_manager_discovery --parallel 6
 Assert-OwnedExit 'Owned step build failed'
}
& ctest --test-dir $build --output-on-failure
Assert-OwnedExit 'Native/fixture tests failed'
$cases=@(
 @('main-step-fixtures-v6-mixed-300','reset-cleared-1000-result.json','original-step-wheel-diagnostics-v6-mixed-300.json'),
 @('main-step-fixtures-posesync-pedals','native-1000.json','original-step-offline-posesync-pedals.json'),
 @('main-step-fixtures-querycycle-pedals','native-1000.json','original-step-offline-querycycle-pedals.json'),
 @('main-step-fixtures-sourceactivation-pedals','native-1000.json','original-step-offline-sourceactivation-pedals.json'),
 @('main-step-fixtures-sourceactivation-mixed-300','native-1000.json','original-step-offline-sourceactivation-mixed-300.json')
)
foreach($case in $cases){
 $folder=Join-Path $recon $case[0]
 $fixture=Join-Path $folder 'owned_control_schedule.tmstep'
 $inputPath=Join-Path $folder 'schedule.tmstepnative'
 & python (Join-Path $PSScriptRoot 'compile_original_step_fixture.py') --fixture $fixture --exe $exe --output $inputPath --report (Join-Path $folder 'compiled.json') --verify-existing
 Assert-OwnedExit 'Native fixture provenance failed'
 & (Join-Path $build 'tm2020_original_step_native.exe') $exe $inputPath (Join-Path $folder $case[1]) --episodes 1000
 Assert-OwnedExit 'Owned reset trace differs'
 if(!$SkipOffline){
  & python (Join-Path $PSScriptRoot 'replay_original_step.py') --exe $exe --fixtures $fixture --report (Join-Path $recon $case[2])
  Assert-OwnedExit 'Guarded offline sequence differs'
 }
}
$mixed=Join-Path $recon 'main-step-fixtures-v6-mixed-300\owned_control_schedule.tmstep'
$pedals=Join-Path $recon 'main-step-fixtures-v6-pedals\owned_control_schedule.tmstep'
& python (Join-Path $PSScriptRoot 'test_owned_step_machine.py') --fixture $mixed --brake-fixture $pedals --exe $exe --report (Join-Path $recon 'owned-interactive-step-qualification.json')
Assert-OwnedExit 'Interactive branch/rewind/reset differs'
& python (Join-Path $PSScriptRoot 'test_owned_step_protocol.py') --fixture $mixed --exe $exe --report (Join-Path $recon 'owned-step-json-protocol.json')
Assert-OwnedExit 'JSON stepping protocol failed'
& python (Join-Path $PSScriptRoot 'test_original_step_native_controls.py') --runner (Join-Path $build 'tm2020_original_step_native.exe') --exe $exe --fixture (Join-Path $recon 'main-step-fixtures-querycycle-pedals\schedule.tmstepnative') --report (Join-Path $recon 'native-pipeline-reset-rejection.json')
Assert-OwnedExit 'Native malformed inputs were accepted'
& python (Join-Path $PSScriptRoot 'reverse_wheel_contact_pipeline.py')
Assert-OwnedExit 'Wheel contact static evidence changed'
& python (Join-Path $PSScriptRoot 'audit_owned_step_continuation.py')
Assert-OwnedExit 'Owned scene/snapshot provenance audit failed'

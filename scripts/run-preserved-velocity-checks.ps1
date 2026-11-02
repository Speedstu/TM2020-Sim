param([switch]$SkipOffline)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$exe='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'
$recon=Join-Path $root 'local\recon'
$runner=Join-Path $root 'native\build\tm2020_original_step_native.exe'
foreach($name in @('source424-rest-throttle','source424-rest-500')){
 $folder=Join-Path $recon ('main-step-fixtures-'+$name)
 $fixture=Join-Path $folder 'owned_control_schedule.tmstep'
 & python (Join-Path $PSScriptRoot 'compile_original_step_fixture.py') --fixture $fixture --exe $exe --output (Join-Path $folder 'schedule.tmstepnative') --report (Join-Path $folder 'compiled.json') --verify-existing
 if($LASTEXITCODE -ne 0){throw 'Preserved-velocity input verification failed'}
 & $runner $exe (Join-Path $folder 'schedule.tmstepnative') (Join-Path $folder 'native-1000.json') --episodes 1000
 if($LASTEXITCODE -ne 0){throw 'Preserved-velocity native reset comparison failed'}
 if(!$SkipOffline){
  & python (Join-Path $PSScriptRoot 'replay_original_step.py') --exe $exe --fixtures $fixture --report (Join-Path $recon ('original-step-offline-'+$name+'.json'))
  if($LASTEXITCODE -ne 0){throw 'Preserved-velocity strict comparison failed'}
 }
}
& python (Join-Path $PSScriptRoot 'audit_preserved_velocity_steps.py')
if($LASTEXITCODE -ne 0){throw 'Preserved-velocity provenance audit failed'}
& (Join-Path $PSScriptRoot 'run-vehicle-substep-checks.ps1') -ObservedReport (Join-Path $recon 'original-step-offline-source424-rest-500.json')
if($LASTEXITCODE -ne 0){throw 'Observed substep comparison failed'}

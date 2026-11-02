param([switch]$SkipOffline)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$exe='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'
$recon=Join-Path $root 'local\recon'
$runner=Join-Path $root 'native\build\tm2020_original_step_native.exe'
function Assert-InputExit([string]$message){if($LASTEXITCODE -ne 0){throw $message}}
foreach($name in @('source424-pedals','source424-mixed-300','source424-input-union')){
 $folder=Join-Path $recon ('main-step-fixtures-'+$name)
 $fixture=Join-Path $folder 'owned_control_schedule.tmstep'
 & python (Join-Path $PSScriptRoot 'compile_original_step_fixture.py') --fixture $fixture --exe $exe --output (Join-Path $folder 'schedule.tmstepnative') --report (Join-Path $folder 'compiled.json') --verify-existing
 Assert-InputExit 'Source input compilation failed'
 & $runner $exe (Join-Path $folder 'schedule.tmstepnative') (Join-Path $folder 'native-1000.json') --episodes 1000
 Assert-InputExit 'Source input native reset comparison failed'
 if(!$SkipOffline){
  & python (Join-Path $PSScriptRoot 'replay_original_step.py') --fixtures $fixture --exe $exe --report (Join-Path $recon ('original-step-offline-'+$name+'.json'))
  Assert-InputExit 'Source input strict replay failed'
 }
}
$union=Join-Path $recon 'main-step-fixtures-source424-input-union\owned_control_schedule.tmstep'
$pedals=Join-Path $recon 'main-step-fixtures-source424-pedals\owned_control_schedule.tmstep'
& python (Join-Path $PSScriptRoot 'test_owned_step_machine.py') --fixture $union --brake-fixture $pedals --exe $exe --report (Join-Path $recon 'owned-source424-interactive.json')
Assert-InputExit 'Source vehicle branch/rewind/reset comparison failed'
& python (Join-Path $PSScriptRoot 'test_owned_step_protocol.py') --fixture $union --exe $exe --report (Join-Path $recon 'owned-source424-protocol.json')
Assert-InputExit 'Source vehicle JSON protocol failed'
& python (Join-Path $PSScriptRoot 'audit_owned_action_grid.py') --fixture $union --exe $exe --runner $runner --output (Join-Path $recon 'owned-source424-action-grid') --report (Join-Path $recon 'owned-source424-action-grid.json')
Assert-InputExit 'Source vehicle action grid comparison failed'
& python (Join-Path $PSScriptRoot 'audit_owned_input_coverage.py')
Assert-InputExit 'Source input provenance audit failed'

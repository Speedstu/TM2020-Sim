$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $root 'cache\temp'
$env:TMP=$env:TEMP
$env:DOTNET_CLI_HOME=Join-Path $root 'cache\dotnet-home'
$env:NUGET_PACKAGES=Join-Path $root 'cache\nuget'
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
$native=Join-Path $root 'native'
$build=Join-Path $native 'build'
$store=Join-Path $root 'local\native-datasets'
$train=Join-Path $build 'tm2020_bc_train.exe'
$checker=Join-Path $build 'tm2020_sdk_test.exe'
$checkpoint=Join-Path $store 'bc-ridge-v1.tmbc'
foreach($p in @($env:TEMP,$env:DOTNET_CLI_HOME,$store)){
 New-Item -ItemType Directory -Path $p -Force | Out-Null
}
Write-Output '[1] Export native format (C++ runtime does not require Python)'
& python (Join-Path $PSScriptRoot 'export_native_dataset.py')
if($LASTEXITCODE -ne 0){throw 'Dataset conversion failed'}
& python (Join-Path $PSScriptRoot 'export_native_splits.py')
if($LASTEXITCODE -ne 0){throw 'Map-UID train/test split failed'}
Write-Output '[2] Compile static SDK + native trainer'
& cmake -S $native -B $build -G 'MinGW Makefiles' -DCMAKE_BUILD_TYPE=Release
if($LASTEXITCODE -ne 0){throw 'CMake configuration failed'}
& cmake --build $build --parallel 4
if($LASTEXITCODE -ne 0){throw 'C++ compilation failed'}
Write-Output '[3] Validate all native maps/replays through the C++ SDK'
$files=@(Get-ChildItem $store -Filter '*.tmmap' -File)
if($files.Count -lt 20){throw "Too few native maps: $($files.Count)"}
foreach($f in $files){
 $base=$f.BaseName
 $rep=Join-Path $store "$base.tmreplay"
 if(-not (Test-Path $rep)){throw "Missing native replay for $base"}
 $test=& $checker $f.FullName $rep 2>&1
 if($LASTEXITCODE -ne 0){throw "C++ test failed for TMX $base : $test"}
}
Write-Output "PASS C++ native map/replay test: $($files.Count) maps"
Write-Output '[4] Train offline imitation model using C++ only'
$result=@(& $train $store $checkpoint 60 2>&1)
if($LASTEXITCODE -ne 0){throw "Native BC training failed: $result"}
$result|ForEach-Object {Write-Output $_}
if(-not (Test-Path $checkpoint)){throw "Native BC checkpoint missing"}
Write-Output '[5] Validate native policy inference and partial geometry'
& $checker (Join-Path $store '365553.tmmap') (Join-Path $store '365553.tmreplay') (Join-Path $root 'local\collision\365553\embedded_physical_shapes.obj') $checkpoint
if($LASTEXITCODE -ne 0){throw 'C++ policy inference failed'}
Write-Output '[6] Ensure invalid/corrupt datasets are rejected'
$invalid=Join-Path $store 'corrupted-test.tmreplay'
try {
  $data=[IO.File]::ReadAllBytes((Join-Path $store '365553.tmreplay'))
  $data[0]=0
  [IO.File]::WriteAllBytes($invalid,$data)
  $null=& $checker (Join-Path $store '365553.tmmap') $invalid 2>&1
  if($LASTEXITCODE -eq 0){throw 'Critical: corrupted replay unexpectedly passed native parser'}
}finally{Remove-Item $invalid -Force -ErrorAction SilentlyContinue}
Write-Output 'PASS C++ corrupt dataset rejection'
# Status checks represent ACTUAL capability, not aspirational checklist completion.
$line=($result|Where-Object {$_ -like 'OFFLINE_BC_NATIVE_CPP20:*'}|Select-Object -First 1)
if(-not $line){throw 'Cannot parse native trainer result'}
$metrics=@{}
foreach($key in @('train_maps','test_maps','train_samples','test_samples','steer_MAE','zero_steer_MAE','gas_accuracy','always_gas_accuracy','brake_accuracy','never_brake_accuracy')){
 $m=[regex]::Match($line,[regex]::Escape($key)+'=([0-9.]+)')
 if(-not $m.Success){throw "Cannot read trainer metric $key"}
 $metrics[$key]=[double]::Parse($m.Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)
}
$gate=[ordered]@{
 schema='tm2020_native_training_status_v1'
 sdkLanguage='C++20'
 nativeMapReplayDatasets=$files.Count
 offlineSupervisedTrainingPipelineWorks=$true
 offlineSupervisedPolicyBeatsNoSteeringBaseline=($metrics['steer_MAE'] -lt $metrics['zero_steer_MAE'])
 offlineSupervisedPolicyQualityReady=$false
 fullStadiumCollisionGeometryReady=$false
 verifiedTrue100HzDynamicsReady=$false
 counterfactualResetStepTrainingEnvironmentReady=$false
 headlessFullPhysicsRLTrainingReady=$false
 inputEventsAreAt10msButVehicleStatesAt50ms=$true
 trainedModel=(Join-Path $store 'bc-ridge-v1.tmbc')
 metrics=$metrics
 comment='C++20 ingestion, BVH and offline imitation training work. Oracle future waypoint is unavailable without planner. No verified full Trackmania physics; not RL-ready.'
}
$report=Join-Path $store 'native-training-readiness.json'
$gate|ConvertTo-Json -Depth 7|Set-Content $report -Encoding UTF8
Write-Output "PASS: native C++ SDK / offline BC pipeline tested. Report: $report"
Write-Output 'STATUS: OFFLINE IMITATION PIPELINE OPERABLE; HIGH-FIDELITY HEADLESS RL ENV NOT READY'
exit 0

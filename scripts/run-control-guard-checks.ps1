param([string]$Executable='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $root 'native\build'
$report=Join-Path $root 'local\recon\control-guard-oracle.json'
New-Item -ItemType Directory -Force (Split-Path -Parent $report) | Out-Null
& cmake -S (Join-Path $root 'native') -B $build
if($LASTEXITCODE -ne 0){throw 'Control guard configure failed'}
& cmake --build $build --target tm2020_control_guard_oracle tm2020_control_guard_test --config Release -j 4
if($LASTEXITCODE -ne 0){throw 'Control guard build failed'}
& ctest --test-dir $build -C Release -R '^recovered_nested_control_guard$' --output-on-failure
if($LASTEXITCODE -ne 0){throw 'Portable control guard regression failed'}
$runner=Join-Path $build 'tm2020_control_guard_oracle.exe'
if(!(Test-Path -LiteralPath $runner)){$runner=Join-Path $build 'Release\tm2020_control_guard_oracle.exe'}
& $runner $Executable $report
if($LASTEXITCODE -ne 0){throw 'Original control guard differential failed'}
$evidence=Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if(!$evidence.bit_exact -or $evidence.cases_per_operation -ne 20000 -or $evidence.operations -ne 3 -or !$evidence.whole_vehicle_bytes_checked){throw 'Incomplete differential evidence'}
& python (Join-Path $PSScriptRoot 'reverse_vehicle_control_fields.py')
if($LASTEXITCODE -ne 0){throw 'Control-field instruction checks failed'}
Write-Output 'PASS CONTROL_GUARD_CHECKS original_operations=3 cases_each=20000 raw_action_mapping=false'

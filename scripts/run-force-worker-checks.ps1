param([switch]$SkipBuild)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $root 'native\build'
$exe='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'
$fixtures=Join-Path $root 'local\recon\force-worker-fixtures-v5'
$reports=Join-Path $root 'local\recon\force-worker-native-v5'
function Assert-ForceExit([string]$message){if($LASTEXITCODE -ne 0){throw $message}}
if(!$SkipBuild){
 & cmake -S (Join-Path $root 'native') -B $build -G 'MinGW Makefiles' -DCMAKE_BUILD_TYPE=Release
 Assert-ForceExit 'Force worker configure failed'
 & cmake --build $build --target tm2020_force_worker_native tm2020_force_fixture_test --parallel 6
 Assert-ForceExit 'Force worker build failed'
}
& (Join-Path $build 'tm2020_force_fixture_test.exe') (Join-Path $build 'force-parser-owned.bin')
Assert-ForceExit 'Sparse fixture parser bounds failed'
$inputs=@(Get-ChildItem -LiteralPath $fixtures -Filter '*.tmforce' | Sort-Object Name | Select-Object -ExpandProperty FullName)
if($inputs.Count -ne 8){throw 'Expected the eight retained private force worker inputs'}
& python (Join-Path $PSScriptRoot 'replay_force_worker.py') --exe $exe --fixtures $inputs --report (Join-Path $root 'local\recon\offline-force-worker-v5.json')
Assert-ForceExit 'Complete original force worker offline replay failed'
New-Item -ItemType Directory -Force $reports | Out-Null
foreach($inputFile in $inputs){
 $name=[IO.Path]::GetFileNameWithoutExtension($inputFile)
 & (Join-Path $build 'tm2020_force_worker_native.exe') $exe $inputFile 10000 (Join-Path $reports ($name+'.json'))
 Assert-ForceExit ('Complete original force worker native differential failed: '+$name)
}
& python (Join-Path $PSScriptRoot 'audit_force_worker.py') --exe $exe --capture (Join-Path $root 'local\recon\force-worker-capture-v5.json') --offline (Join-Path $root 'local\recon\offline-force-worker-v5.json') --fixtures $fixtures --native $reports --report (Join-Path $root 'local\recon\force-worker-qualification.json')
Assert-ForceExit 'Complete force worker provenance/output audit failed'

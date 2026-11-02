param([string]$ObservedReport='')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $root 'native\build'
& cmake -S (Join-Path $root 'native') -B $build
if($LASTEXITCODE -ne 0){throw 'Vehicle substep configure failed'}
& cmake --build $build --target tm2020_vehicle_substep_probe tm2020_vehicle_motion_probe tm2020_vehicle_substep_test --parallel 6
if($LASTEXITCODE -ne 0){throw 'Vehicle substep build failed'}
& ctest --test-dir $build -R '^recovered_vehicle_substep_selection$' --output-on-failure
if($LASTEXITCODE -ne 0){throw 'Vehicle substep regression failed'}
$oracleArgs=@('--exe','D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe',
 '--runner',(Join-Path $build 'tm2020_vehicle_substep_probe.exe'),
 '--output',(Join-Path $root 'local\recon\vehicle-substep-selector'),
 '--report',(Join-Path $root 'local\recon\vehicle-substep-selector-oracle.json'))
& python (Join-Path $PSScriptRoot 'oracle_vehicle_substeps.py') @oracleArgs
if($LASTEXITCODE -ne 0){throw 'Original instruction vehicle substep comparison failed'}
if($ObservedReport){
 & python (Join-Path $PSScriptRoot 'oracle_vehicle_substeps.py') --exe 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' --runner (Join-Path $build 'tm2020_vehicle_substep_probe.exe') --output (Join-Path $root 'local\recon\vehicle-substep-selector-observed') --report (Join-Path $root 'local\recon\vehicle-substep-selector-observed-oracle.json') --observed-report $ObservedReport
 if($LASTEXITCODE -ne 0){throw 'Observed scene substeps differ from portable arithmetic'}
}
& python (Join-Path $PSScriptRoot 'oracle_vehicle_motion.py') --exe 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' --runner (Join-Path $build 'tm2020_vehicle_motion_probe.exe') --output (Join-Path $root 'local\recon\vehicle-substep-motion') --report (Join-Path $root 'local\recon\vehicle-substep-motion-oracle.json')
if($LASTEXITCODE -ne 0){throw 'Original instruction four-vector motion comparison failed'}

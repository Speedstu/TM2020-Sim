$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$root = $script:RepoRoot
& (Join-Path $PSScriptRoot 'build.ps1')
if($LASTEXITCODE -ne 0){ throw 'build failed' }
& (Join-Path $PSScriptRoot 'smoke-test.ps1')
if($LASTEXITCODE -ne 0){ throw 'map tests failed' }
foreach($id in @(5006,4988,4992,5009)){
 $gbx=Join-Path $root ("local\replays\tmtas-$id.Replay.Gbx")
 $data=Join-Path $root ("local\replays\dataset-$id.json")
 & (Join-Path $PSScriptRoot 'gbx.ps1') -Command dataset -Path $gbx -Output $data
 if($LASTEXITCODE -ne 0){ throw "replay $id failed" }
}
$files = @(5006,4988,4992,5009) | ForEach-Object {Join-Path $root ("local\replays\dataset-$_.json")}
$report = Join-Path $root 'local\replays\validation-all.json'
$env:PYTHONDONTWRITEBYTECODE='1'
& python (Join-Path $PSScriptRoot 'validate_dataset.py') @files --output $report | Out-Null
if($LASTEXITCODE -ne 0){ throw 'dataset validation failed' }
$reports = (Get-Content $report -Raw|ConvertFrom-Json).reports
$stats = @($reports|ForEach-Object {$_.ghosts}|Where-Object {$_.rows -gt 0})
$rows = ($stats|Measure-Object -Property rows -Sum).Sum
$inputs = ($stats|Measure-Object -Property inputEvents -Sum).Sum
$bad = ($stats|Measure-Object -Property nonMonotonicSampleTimes -Sum).Sum
$nonfinite = ($stats|Measure-Object -Property nonFiniteStateRows -Sum).Sum
if($bad -gt 0 -or $nonfinite -gt 0){throw "bad replay data: steps=$bad nonfinite=$nonfinite"}
& python (Join-Path $PSScriptRoot 'make_dataset_manifest.py')
if($LASTEXITCODE -ne 0){throw 'map/replay UID linkage failed'}
Write-Output "PASS all: $($stats.Count) replays; $rows state rows; $inputs input events; 0 invalid state rows"
Write-Output "Quality report: $report"

# Additional native geometry and offline physics quality gates.
& (Join-Path $PSScriptRoot 'build-raycaster.ps1')
if($LASTEXITCODE -ne 0){throw 'raycaster build/test failed'}
$env:PYTHONDONTWRITEBYTECODE='1'
& python (Join-Path $PSScriptRoot 'physics_baseline.py') | Out-Null
if($LASTEXITCODE -ne 0){throw 'physics baseline failed'}
& python (Join-Path $PSScriptRoot 'build_collision_map.py') 365553 364956 361930 2154 | Out-Null
if($LASTEXITCODE -ne 0){throw 'partial world collision build failed'}
$ray=Join-Path $root 'bin\trackray.exe'
foreach($id in @(365553,364956)) {
 $obj=Join-Path $root "local\collision\$id\embedded_physical_shapes.obj"
 $result=& $ray $obj --verify 1000 | ConvertFrom-Json
 if($LASTEXITCODE -ne 0 -or $result.hitRatio -lt 0.99){throw "raycast verification failed on $id"}
 Write-Output ("PASS raycaster TMX {0}: {1} tris, {2:N0} rays/s, {3:P1} hit fraction" -f $id,$result.triangles,$result.raysPerSecond,$result.hitRatio)
}
& python (Join-Path $PSScriptRoot 'validate_collision_coverage.py') | Out-Null
if($LASTEXITCODE -ne 0){throw 'ground ray coverage test failed'}
Write-Output 'PASS all geometry + dataset + cross-map physics validation tools'

# Python <-> C++ native SDK, map-UID grouping and 10ms input-event calibration.
& (Join-Path $PSScriptRoot 'build-raycaster-library.ps1')
if($LASTEXITCODE -ne 0){throw 'native raycaster DLL compilation failed'}
& python (Join-Path $PSScriptRoot 'test_sdk.py')
if($LASTEXITCODE -ne 0){throw 'Python SDK tests failed'}
& python (Join-Path $PSScriptRoot 'calibrate_inputs.py')
if($LASTEXITCODE -ne 0){throw 'Input timing calibration failed'}
$calibration=Get-Content (Join-Path $root 'local\input_calibration.json') -Raw|ConvertFrom-Json
if($calibration.heldoutReferenceFormula2xMinus1Over255.count -le 100){ throw 'Input validation has too few heldout frames' }
Write-Output 'PASS: native Python BVH, 24-map SDK tests, and heldout input calibration'

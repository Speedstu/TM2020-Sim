param(
    [switch]$ConfirmLocalSolo,
    [ValidateRange(128,1024)][int]$ScanMegabytes=768,
    [ValidateRange(10,2000)][int]$Samples=150
)
# Native C++20 only at runtime: captures numeric candidate triples and
# bootstraps a PID+SHA+creation-time-bound V3 experimental pose manifest.
# Does not inject any code, send game inputs, or start a game process.
$ErrorActionPreference='Stop'
if(-not $ConfirmLocalSolo){
 throw 'Explicitly use -ConfirmLocalSolo while at the start of a local offline Solo map.'
}
$root=Split-Path -Parent $PSScriptRoot
$bin=Join-Path $root 'native\build'
$map=Join-Path $root 'local\campaign-2026-autumn\361913.tmmap'
$outDir=Join-Path $root 'local\recon'
$env:TEMP=Join-Path $root 'cache\temp'
$env:TMP=$env:TEMP
if(!(Test-Path $map)){throw 'Expected Nadeo Fall 2026 - 01 native map not found'}
$proc=@(Get-Process Trackmania -ErrorAction SilentlyContinue)
if($proc.Count -ne 1){throw 'Expected a single running Trackmania process'}
$pidNumber=$proc[0].Id
$tag='live-cpp-'+$pidNumber
$snapshot=Join-Path $outDir "$tag.tmvec"
$manifest=Join-Path $outDir "$tag-v3.txt"
$csv=Join-Path $outDir "$tag.csv"
foreach($program in @('tm2020_live_vector_probe.exe','tm2020_bootstrap_map.exe','tm2020_pose_reader.exe')){
 if(!(Test-Path (Join-Path $bin $program))){throw "Build the native SDK first: missing $program"}
}
Write-Output "=== Read-only native Solo capture (PID $pidNumber) ==="
& (Join-Path $bin 'tm2020_live_vector_probe.exe') --capture $snapshot $ScanMegabytes
if($LASTEXITCODE -ne 0){throw 'Numeric-only process candidate capture failed'}
Write-Output '=== Native C++ GBX-anchored pose bootstrap (NO PYTHON) ==='
& (Join-Path $bin 'tm2020_bootstrap_map.exe') --bootstrap $map $snapshot $manifest
if($LASTEXITCODE -ne 0){throw 'Failed to find enough independent position candidates at GBX start'}
Write-Output '=== Native C++ game-process pose consensus (no writes) ==='
& (Join-Path $bin 'tm2020_pose_reader.exe') --sample $manifest $csv $Samples
if($LASTEXITCODE -ne 0){throw 'Position replicas disagree or manifest became stale'}
$rows=@(Import-Csv $csv)
if($rows.Count -ne $Samples){throw "Expected $Samples observations, got $($rows.Count)"}
$valid=@($rows|Where-Object {
 [int]$_.agreement -ge 4 -and [int]$_.candidate_orientation_copies -ge 4 -and
 $_.vehicle_state_verified -eq 'false' -and $_.orientation_verified -eq 'false'
})
if($valid.Count -lt [math]::Ceiling($Samples*.90)){
 throw 'Numeric pose/quaternion candidates do not consistently agree'
}
Write-Output "PASS NATIVE_OFFLINE_CPP_BOOTSTRAP valid=$($valid.Count)/$Samples pid=$pidNumber manifest=$manifest"
Write-Output 'LIMITATION: This is not authoritative 100Hz physics, a validated car owner, or an RL-ready simulator.'

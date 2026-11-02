# Finish one read-only numeric-vector motion test after the user manually drives.
# Does not send inputs, inject code, access Ubisoft credentials or modify game.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$exe=Join-Path $root 'native\build\tm2020_live_vector_probe.exe'
$rank=Join-Path $PSScriptRoot 'rank_live_motion_candidates.py'
$dir=Join-Path $root 'local\recon'
$first=Join-Path $dir 'stationary-solo-track01.tmvec'
$second=Join-Path $dir 'stationary-solo-track01-second.tmvec'
$after=Join-Path $dir 'moved-solo-track01.tmvec'
$out=Join-Path $dir 'motion-position-hypotheses.json'
foreach($file in @($exe,$rank,$first,$second)){if(!(Test-Path $file)){throw "Missing prior session or probe file: $file"}}
$running=@(Get-Process Trackmania -ErrorAction SilentlyContinue)
if($running.Count -ne 1){throw 'Expected exactly one active Trackmania instance. Do not reuse old snapshots after restart.'}
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $root 'cache\temp'
$env:TMP=$env:TEMP
Write-Output 'Comparing motion against two prior stationary baseline measurements.'
& $exe --capture $after 768
if($LASTEXITCODE -ne 0){throw 'Read-only live moving snapshot failed'}
& python $rank --before $first --still $second --after $after --out $out
if($LASTEXITCODE -ne 0){throw 'Read-only live motion ranking failed'}
$analysis=Get-Content $out -Raw|ConvertFrom-Json
Write-Output "COMMON vectors: $($analysis.commonTriplets)"
Write-Output "HYPOTHETICAL moved vectors: $($analysis.stableAtRestAndMovedCandidates)"
Write-Output "ACTUAL CAR POSITION CONFIRMED: $($analysis.actualVehiclePositionProven)"
if($analysis.stableAtRestAndMovedCandidates -eq 0){
 Write-Warning 'No moving position candidates found. The game may not have moved, or the numeric filter missed the vehicle.'
}
Write-Output "RESULT $out"

# Research-only tests of the read-only Trackmania C++ pose candidate reader.
# No interaction with game controls, no DLL injection and no process writes.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$exe=Join-Path $root 'native\build\tm2020_pose_reader.exe'
$manifest=Join-Path $root 'local\recon\session-pose-candidates-v3.txt'
$csv=Join-Path $root 'local\recon\pose-reader-regression.csv'
$tempDir=Join-Path $root 'cache\pose-reader-rejection-tests'
if(!(Test-Path $exe)){throw 'Missing native pose reader binary'}
New-Item $tempDir -ItemType Directory -Force | Out-Null
& $exe --selftest
if($LASTEXITCODE -ne 0){throw 'Native pose reader selftest failed'}
$game=@(Get-Process Trackmania -ErrorAction SilentlyContinue)
if($game.Count -eq 0 -or -not(Test-Path $manifest)){
 Write-Output 'PASS selftest; live pose sampling skipped because game/manifest not available'
 exit 0
}
$lines=[IO.File]::ReadAllLines($manifest)
$manifestPid=[int]$lines[1]
$gamePid=[int]$game[0].Id
if($gamePid -ne $manifestPid){
 Write-Output "PASS selftest; game process restarted PID=$gamePid; refusing stale manifest PID=$manifestPid"
 exit 0
}
& $exe --sample $manifest $csv 40
if($LASTEXITCODE -ne 0){throw 'Read-only real-game numeric candidate consensus failed'}
$records=@(Import-Csv $csv)
if($records.Count -ne 40){throw 'Expected 40 real-game numeric samples'}
if(@($records|Where-Object {[int]$_.agreement -lt 5 -or $_.vehicle_state_verified -ne 'false' -or
    [int]$_.candidate_orientation_copies -lt 4 -or $_.orientation_verified -ne 'false'}).Count){
 throw 'Pose/quaternion candidate quorum insufficient, or incorrectly labeled confirmed car physics'
}
# Negative controls: each corrupted manifest must FAIL before sampling.
# PowerShell array indexes 0: header, 1: PID, 2: creation, 3: sha, 4: layout.
$idx=@{WrongPID=1;WrongExeHash=3;WrongCreationTime=2;WrongAxisLayout=4}
try {
 foreach($test in $idx.Keys){
  $copy=@($lines)
  switch($test){
   WrongPID {$copy[1]=([long]$copy[1]+1).ToString()}
   WrongExeHash {$copy[3]=if($copy[3][0] -eq 'a'){'b'+$copy[3].Substring(1)}else{'a'+$copy[3].Substring(1)}}
   WrongCreationTime {$copy[2]=([long]$copy[2]+1).ToString()}
   WrongAxisLayout {$copy[4]='ZYX_INVALID'}
  }
  $bad=Join-Path $tempDir "$test.txt"
  [IO.File]::WriteAllLines($bad,$copy)
  $logs=@(& $exe --sample $bad (Join-Path $tempDir "$test.csv") 10 2>&1)
  if($LASTEXITCODE -eq 0){throw "CRITICAL bad manifest unexpectedly accepted: $test"}
  Write-Output "PASS reject $test"
 }
}finally {
 Get-ChildItem $tempDir -File -ErrorAction SilentlyContinue|Remove-Item -Force -ErrorAction SilentlyContinue
}
Write-Output 'PASS native C++ reader: validated live consensus, build hash, process identity and negative controls'
exit 0

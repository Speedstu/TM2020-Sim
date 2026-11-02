$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source=Join-Path $root 'src\geometry\trackray.cpp'
$out=Join-Path $root 'bin\trackray.exe'
$temp=Join-Path $root 'cache\temp'
New-Item -ItemType Directory -Force (Split-Path $out -Parent),$temp | Out-Null
$env:TEMP=$temp
$env:TMP=$temp
g++ -O3 -std=c++20 -Wall -Wextra -o $out $source
if ($LASTEXITCODE -ne 0) { throw 'C++ raycaster compilation failed' }
$testDir=Join-Path $root 'local\tests'
New-Item -ItemType Directory -Force $testDir|Out-Null
$obj=Join-Path $testDir 'one-triangle.obj'
@'
v 0 0 0
v 1 0 0
v 0 1 0
f 1 2 3
'@ | Set-Content -Path $obj -Encoding UTF8
$raw=& $out $obj --probe 0.25 0.25 1 0 0 -1 2
if($LASTEXITCODE -ne 0){throw 'raycaster probe failed'}
$hit=$raw|ConvertFrom-Json
if(-not $hit.hit -or [math]::Abs([double]$hit.distance-1.0) -gt 0.00000001){
 throw "raycaster selftest incorrect: $raw"
}
"PASS: C++20 raycaster built at $out and unit ray test passed"

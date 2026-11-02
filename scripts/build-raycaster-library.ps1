$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source=Join-Path $root 'src\geometry\trackray.cpp'
$output=Join-Path $root 'bin\TrackrayNative.dll'
$temp=Join-Path $root 'cache\temp'
New-Item -ItemType Directory -Force (Split-Path $output -Parent),$temp | Out-Null
$env:TEMP=$temp
$env:TMP=$temp
g++ -O3 -std=c++20 -Wall -Wextra -DTRACKRAY_LIBRARY -shared -static -static-libgcc -static-libstdc++ -o $output $source
if ($LASTEXITCODE -ne 0) { throw 'Native DLL compilation failed' }
"PASS native BVH DLL compiled: $output"

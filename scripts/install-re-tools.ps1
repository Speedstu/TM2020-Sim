$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$version='6.2.4'
$name="radare2-$version-w64.zip"
$url="https://github.com/radareorg/radare2/releases/download/$version/$name"
# Digest supplied by the official GitHub release asset metadata.
$sha='aa3454fd89e8a4ead450caff35a1d3919065744e7091540d4913a9487241799d'
$archive=Join-Path $root "cache\$name"
$destination=Join-Path $root "tools\radare2-$version"
New-Item -ItemType Directory -Force (Split-Path -Parent $archive) | Out-Null
if(!(Test-Path -LiteralPath $archive)){Invoke-WebRequest -Uri $url -OutFile $archive}
if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha){throw 'radare2 release SHA-256 mismatch'}
if(!(Test-Path -LiteralPath $destination)){Expand-Archive -LiteralPath $archive -DestinationPath $destination}
$exe=Join-Path $destination "radare2-$version-w64\bin\radare2.exe"
& $exe -v
if($LASTEXITCODE -ne 0){throw 'Portable radare2 failed to start'}
Write-Output "VERIFIED_PORTABLE_RE_TOOL path=$exe release=$url sha256=$sha"

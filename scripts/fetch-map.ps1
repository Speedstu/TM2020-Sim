param(
  [Parameter(Mandatory)][ValidateRange(1,9999999)][int]$Id
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$folder = Join-Path $script:RepoRoot 'local\test-maps'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$map = Join-Path $folder ("tmx-{0}.Map.Gbx" -f $Id)
$url = "https://trackmania.exchange/mapgbx/$Id"
if(-not (Test-Path $map)){
  Invoke-WebRequest -Uri $url -OutFile $map -MaximumRedirection 5 -TimeoutSec 35
}
$file = Get-Item $map
if ($file.Length -lt 16 -or $file.Length -gt 30MB) { throw "Unexpected file size: $($file.Length)" }
$fs = [IO.File]::OpenRead($map)
try {
  $head = New-Object byte[] 3
  $null = $fs.Read($head,0,3)
  if ([Text.Encoding]::ASCII.GetString($head) -ne 'GBX') {throw 'Download is not GBX'}
} finally { $fs.Dispose() }
Write-Host "GBX available: $map ($($file.Length) bytes)"
& (Join-Path $PSScriptRoot 'gbx.ps1') -Command map -Path $map -Output (Join-Path $folder ("tmx-{0}.json" -f $Id))
exit $LASTEXITCODE

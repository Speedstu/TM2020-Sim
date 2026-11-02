param(
 [Parameter(Mandatory)][ValidateRange(1,99999999)][int]$Id
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$folder = Join-Path $script:RepoRoot 'local\replays'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$file = Join-Path $folder ("tmtas-$Id.Replay.Gbx")
if(-not (Test-Path $file)) {
    Invoke-WebRequest -Uri "https://tmtas.exchange/api/replay?id=$Id" -OutFile $file -TimeoutSec 35 -MaximumRedirection 4
}
$item = Get-Item $file
if ($item.Length -lt 100 -or $item.Length -gt 30MB) { throw "Unexpected replay size: $($item.Length)" }
$fs=[IO.File]::OpenRead($file)
try {
 $bytes=New-Object byte[] 3
 $null=$fs.Read($bytes,0,3)
 if([Text.Encoding]::ASCII.GetString($bytes) -ne 'GBX') { throw 'Downloaded replay has no GBX signature' }
} finally {$fs.Dispose()}

$dataset=Join-Path $folder ("dataset-$Id.json")
& (Join-Path $PSScriptRoot 'gbx.ps1') -Command dataset -Path $file -Output $dataset
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
$env:PYTHONDONTWRITEBYTECODE='1'
$validation=Join-Path $folder ("validation-$Id.json")
python (Join-Path $PSScriptRoot 'validate_dataset.py') $dataset --output $validation
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
Write-Output "REPLAY_IMPORTED: $Id"

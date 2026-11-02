param(
 [ValidateSet('map','scan','replay','record-schema','dataset','map-schema','embedded','embedded-extract','mesh-extract','pe','pak')][string]$Command = 'scan',
 [Parameter(Mandatory)][string]$Path,
 [string]$Output = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$dll = Join-Path $script:RepoRoot 'src\GbxLab\bin\Release\net9.0\GbxLab.dll'
if(-not (Test-Path $dll)){ throw "Not built. Run scripts\build.ps1 first." }
if($Output){ dotnet $dll $Command $Path $Output } else { dotnet $dll $Command $Path }
exit $LASTEXITCODE

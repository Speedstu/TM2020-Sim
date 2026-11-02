$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$proj = Join-Path $script:RepoRoot 'src\GbxLab\GbxLab.csproj'
dotnet restore $proj --configfile (Join-Path $script:RepoRoot 'NuGet.Config') --nologo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
dotnet build $proj --configuration Release --no-restore --nologo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

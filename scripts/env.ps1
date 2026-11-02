# Project-local caches and temp; no global tool configuration or Python environments.
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$env:DOTNET_CLI_HOME = Join-Path $script:RepoRoot 'cache\dotnet-home'
$env:NUGET_PACKAGES = Join-Path $script:RepoRoot 'cache\nuget'
$env:NUGET_HTTP_CACHE_PATH = Join-Path $script:RepoRoot 'cache\nuget-http'
$env:TEMP = Join-Path $script:RepoRoot 'cache\temp'
$env:TMP = $env:TEMP
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$env:DOTNET_ADD_GLOBAL_TOOLS_TO_PATH = 'false'
$env:NUGET_XMLDOC_MODE = 'skip'
foreach ($dir in @($env:DOTNET_CLI_HOME, $env:NUGET_PACKAGES, $env:NUGET_HTTP_CACHE_PATH, $env:TEMP)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

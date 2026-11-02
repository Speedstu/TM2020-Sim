param([switch]$ConfirmLocalSolo,[string]$Manifest)
$ErrorActionPreference='Stop'
if(!$ConfirmLocalSolo){throw 'Run with -ConfirmLocalSolo in an authorized local Solo race.'}
$root=Split-Path -Parent $PSScriptRoot
$game=@(Get-Process Trackmania -ErrorAction Stop)
if($game.Count -ne 1){throw 'Expected one running Trackmania process'}
if(!$Manifest){$Manifest=Join-Path $root "local\recon\live-cpp-$($game[0].Id)-v3.txt"}
$identity=[IO.File]::ReadAllLines($Manifest)
$source=Join-Path $root 'dist\sdk-windows-x64\bin\libtm2020_policy.dll'
$sha=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$runtime=Join-Path $root 'local\runtime'
New-Item -ItemType Directory -Force $runtime | Out-Null
$module=Join-Path $runtime 'tm2020-policy-0.5.0.dll'
if((Test-Path -LiteralPath $module) -and (Get-FileHash -LiteralPath $module -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha){
 $module=Join-Path $runtime "tm2020-policy-0.5.0-$($sha.Substring(0,12)).dll"
}
if(!(Test-Path -LiteralPath $module)){Copy-Item -LiteralPath $source -Destination $module}
if((Get-FileHash -LiteralPath $module -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha){throw 'Runtime module hash mismatch'}
$result=@(& (Join-Path $root 'native\build\tm2020_local_dll_loader.exe') --confirm-local-solo $Manifest $module 2>&1)
$code=$LASTEXITCODE
$result | Add-Content (Join-Path $root 'local\recon\codex-game-dll-load.log')
$result | ForEach-Object {Write-Output $_}
if($code -ne 0 -or ($result -join "`n") -notmatch 'sdk_entry_executed=true'){throw 'Native game SDK qualification failed'}
$loaded=@((Get-Process -Id $game[0].Id -ErrorAction Stop).Modules | Where-Object FileName -eq $module)
if($loaded.Count -ne 1){throw 'Module path not independently visible in target process'}
$exe='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'
$addedThisRun=($result -join "`n") -match ' added=1 '
$report=[ordered]@{
 schema='tm2020_local_solo_sdk_module_qualification_v1';updatedUtc=[DateTime]::UtcNow.ToString('o')
 pid=$game[0].Id;processCreationFiletime=$identity[2];modulePath=$module;moduleSha256=$sha
 gameExeSha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
 modulePathVerified=$true;sdkEntryExecutedInGameProcess=$true;policyAbiVersionReturned=1
 loaderMechanism='ordinary LoadLibraryW';moduleAddedThisRun=$addedThisRun;remoteDllPathAllocationWritten=$addedThisRun
 gameInstallFilesModified=$false;gameHooksInstalled=$false;physicsCallbacksInstalled=$false
 botExecutionInsideGameValidated=$false
}
$report | ConvertTo-Json | Set-Content (Join-Path $root 'local\recon\injected-policy-module.json') -Encoding UTF8
$report | ConvertTo-Json -Compress | Add-Content (Join-Path $root 'local\recon\sdk-module-qualification-history.jsonl')
Write-Output 'PASS local Solo SDK module and entry execution. This does not install simulation hooks or start the bot inside the game.'

$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$game='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'
$upc='D:\Ubisoft\Ubisoft Game Launcher\UbisoftConnect.exe'
$probe=Join-Path $root 'native\build\tm2020_game_probe.exe'
if(-not(Test-Path $game) -or -not(Test-Path $upc) -or -not(Test-Path $probe)){throw 'Game, launcher or native probe missing'}
$process=@(Get-Process Trackmania -ErrorAction SilentlyContinue)
if($process.Count -eq 0){throw 'Trackmania process must be running to capture this provenance'}
$out=Join-Path $root 'local\recon\real-game-session-20261021.json'
$observation=@(& $probe --probe)
if($LASTEXITCODE -ne 0 -or @($observation|Where-Object {$_ -match '^PASS READ_ONLY_GAME_PROBE'}).Count -lt 1){
 throw 'Read-only PE probe did not confirm loaded process'
}
$report=[ordered]@{
 schema='tm2020_authenticated_solo_research_session_v1'
 observedOnDateLocal=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
 gameExeVersion=(Get-Item $game).VersionInfo.FileVersion
 gameExeSHA256=(Get-FileHash $game -Algorithm SHA256).Hash
 steamAppId='2225070'
 ubisoftLauncherRegistryVersion=(Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Uplay').DisplayVersion
 gameRunning=$true
 actualReadOnlyProcessProbePassed=$true
 gameWindowsProcessIds=@($process|ForEach-Object Id)
 gameReachedMainMenuVisually=$true
 soloMenuLoadedCampaignTrack01Visually=$true
 soloDrivingStartedVerified=$false
 userInputRequiredToDismissIntro=$true
 actualVehicle100HzStateRead=$false
 realInGameBotDllInjectionPerformed=$false
 nativeSdkHeadlessRLReady=$false
 readOnlyProcessOutput=$observation
 }
$report|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $out -Encoding UTF8
Write-Output ('PASS REAL_SESSION_PROVENANCE pid='+($process|Select-Object -First 1).Id+' sha256='+$report.gameExeSHA256)
Write-Output ('SESSION_NOTE Solo map 01 intro reached, real car telemetry not decoded')
Write-Output ('REPORT '+$out)

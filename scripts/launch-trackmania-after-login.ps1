# User-run: start Trackmania through Steam after Ubisoft Connect sign-in.
# Never collects usernames, passwords, tokens or login window screenshots.
# No DLL injection or gameplay automation. Log/report files only under H:.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$steam='C:\Program Files (x86)\Steam\steam.exe'
$ubisoft='D:\Ubisoft\Ubisoft Game Launcher\UbisoftConnect.exe'
$game='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'
$probe=Join-Path $root 'native\build\tm2020_game_probe.exe'
$log=Join-Path $root 'local\recon\steam-local-launch-preflight.json'
if(-not(Test-Path $steam)){throw 'Steam missing from expected installed location'}
if(-not(Test-Path $ubisoft)){throw 'Ubisoft Connect missing on D:; install first'}
if(-not(Test-Path $game)){throw 'Trackmania Steam executable missing'}
if(-not(Test-Path $probe)){throw 'Native game probe missing; build SDK first'}
$ubi=Get-Item $ubisoft
$running=@(Get-Process -Name upc -ErrorAction SilentlyContinue)
if($running.Count -eq 0){
 Write-Output 'Ubisoft Connect is not running. Launch it and sign in before this test.'
 Start-Process -FilePath $ubisoft -WorkingDirectory (Split-Path $ubisoft -Parent) | Out-Null
 exit 2
}
$existed=@(Get-Process -Name Trackmania -ErrorAction SilentlyContinue)
if($existed.Count -eq 0){
 Write-Output 'Launching Steam app 2225070 / installed Trackmania 2020 (normal user session).'
 Start-Process -FilePath $steam -ArgumentList '-applaunch 2225070' -WorkingDirectory (Split-Path $steam -Parent) | Out-Null
}
$started=$false
for($i=0;$i -lt 40;$i++){
 Start-Sleep -Milliseconds 750
 $gameProcess=@(Get-Process -Name Trackmania -ErrorAction SilentlyContinue)
 if($gameProcess.Count -gt 0){$started=$true;break}
}
$probeOutput=if($started){@(& $probe '--probe')}else{@('NOT_RUNNING')}
$report=[ordered]@{
 schema='tm2020_steam_local_launch_preflight_v1'
 steamAppId='2225070'
 gameExists=(Test-Path $game)
 gameVersion=(Get-Item $game).VersionInfo.FileVersion
 ubisoftLauncherVersion=$ubi.VersionInfo.FileVersion
 ubisoftLauncherRunning=$true
 gameProcessStarted=$started
 authenticatedAndEnteredLocalRaceVerified=$false
 physicalTelemetryCaptured=$false
 gameInjectionPerformed=$false
 readOnlyProcessProbeResult=$probeOutput
 note='This script neither signs in to Ubisoft nor checks a multiplayer game mode. It ONLY launches through Steam and uses a read-only module probe.'
}
$report|ConvertTo-Json -Depth 4|Set-Content $log -Encoding UTF8
Write-Output ('GAME_PROCESS_STARTED='+$started)
$probeOutput
Write-Output "SAVED $log"
if(-not $started){Write-Warning 'Trackmania failed to start. Check Ubisoft Connect authentication and any game dialog.';exit 3}
exit 0

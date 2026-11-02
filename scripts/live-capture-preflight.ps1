# Read-only prerequisite inspection; produces JSON only in H: workspace.
# Does not install Openplanet, write to C:, change Trackmania or launch a game.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$game='D:\SteamLibrary\steamapps\common\Trackmania'
$exe=Join-Path $game 'Trackmania.exe'
$plugin=Join-Path $root 'openplanet\TM2020PhysicsLab\Main.as'
$collector=Join-Path $root 'native\build\tm2020_capture.exe'
$plugInGame=Join-Path $game 'Openplanet'
$hook=Join-Path $game 'dinput8.dll'
$profilePlugin=Join-Path $env:USERPROFILE 'OpenplanetNext\Plugins'
$opReady=(Test-Path $plugInGame) -and (Test-Path $hook)
$runtimeReady=(Get-Process -Name Trackmania -ErrorAction SilentlyContinue| Measure-Object).Count -gt 0
$info=[ordered]@{
 schema='tm2020_live_instrumentation_preflight_v1'
 gameExecutablePresent=(Test-Path $exe)
 gameVersion=if(Test-Path $exe){(Get-Item $exe).VersionInfo.FileVersion}else{$null}
 openplanetLoaderDetected=$opReady
 openplanetPluginProfileExists=(Test-Path $profilePlugin)
 passivePluginSourcePresent=(Test-Path $plugin)
 nativeLoopbackCollectorPresent=(Test-Path $collector)
 runningTrackmania=$runtimeReady
 livePhysicsCapturePerformed=$false
 actualGameVsSdkPhysicsCalibrationReady=$false
 projectStorageDrive='H:'
 gameStorageDrive='D:'
 doesNotWriteToWindowsProfile=$true
 note='This preflight writes only a report to H:, never installs Openplanet and never launches/modifies Trackmania. Current plugin source passes static checks but needs an opt-in runtime setup.'
}
$out=Join-Path $root 'local\live-capture-preflight.json'
$info|ConvertTo-Json -Depth 3|Set-Content $out -Encoding UTF8
Write-Output "GAME found: $($info.gameExecutablePresent) | OP loader: $($info.openplanetLoaderDetected) | plugin source: $($info.passivePluginSourcePresent) | game running: $runtimeReady"
Write-Output "RESULT: $out"
if(-not $opReady){Write-Output 'BLOCKED: Official Openplanet is not installed. No automatic installer execution or files created on C:.'}

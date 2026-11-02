param(
 [switch]$ConfirmLocalSolo,
 [ValidateRange(1,100)][int]$Episodes=3,
 [ValidateRange(5,120)][int]$Seconds=40,
 [string]$Model,
 [switch]$Evaluate,
 [double]$Deadzone=0.1,
 [string]$ViGEmClient
)
$ErrorActionPreference='Stop'
if(!$ConfirmLocalSolo){throw 'Explicit -ConfirmLocalSolo required; keep the local Solo game in foreground.'}
$root=Split-Path -Parent $PSScriptRoot
if(!$Model){$Model=Join-Path $root 'local\native-datasets\live-residual-v1.tmppo'}
$Model=[IO.Path]::GetFullPath($Model)
$game=Get-Process Trackmania -ErrorAction Stop | Select-Object -First 1
$manifest=Join-Path $root "local\recon\live-cpp-$($game.Id)-v3.txt"
$reference=Join-Path $root 'local\campaign-2026-autumn\native-replays\4634.tmreplay'
$vigem=if($ViGEmClient){[IO.Path]::GetFullPath($ViGEmClient)}else{Join-Path $root 'tools\vigem\ViGEmClient.dll'}
$driver=Join-Path $root 'native\build\tm2020_live_drive.exe'
$stamp=[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
for($episode=0;$episode -lt $Episodes;$episode++){
 $trace=Join-Path $root "local\recon\codex-follower-ppo-$stamp-$episode.csv"
 $mode=if($Evaluate){'--ppo-evaluate'}else{'--ppo-update'}
 & $driver --confirm-local-solo $manifest $reference $trace gamepad $vigem $Seconds 24 -3 --tracking --deadzone ($Deadzone.ToString([Globalization.CultureInfo]::InvariantCulture)) $mode $Model
 $code=$LASTEXITCODE
 if(Test-Path -LiteralPath ($trace+'.ppo.csv')){Import-Csv -LiteralPath ($trace+'.ppo.csv') | Format-List}
 if($code -ne 0){throw 'Session stopped; any completed on-policy prefix and its update remain in the trace sidecars. Fix the runtime precondition before continuing.'}
}
Write-Output 'PPO sessions returned. Inspect retained metrics and independent evaluation; these runs alone do not demonstrate improved race strength.'
